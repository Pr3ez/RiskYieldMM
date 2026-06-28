"""Regime and change-risk diagnostics for ranked-signal router runs.

This command is diagnostic-only.  It consumes completed ``rank_signal_router``
runs and builds prediction-time-safe regime context rows, past-only latent
state assignments, online change alarms, and post-hoc signal-quality summaries.

The intended use is to answer whether UP/DOWN ranker quality is conditional on
market/context regimes before wiring any regime logic into the live router.
Current prediction labels are never written into ``regime_context.parquet``.
They appear only in outcome/quality artifacts.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from regression_feature_engineering.walkforward.ablation import FAMILY_PREFIXES
from regression_feature_engineering.walkforward.config import DEFAULT_CONFIG_PATH, load_clean_config
from regression_feature_engineering.walkforward.data import available_batch_ids, resolve_context
from regression_feature_engineering.walkforward.policy import load_panel_features
from regression_feature_engineering.walkforward.rank_signal import write_rows_parquet
from regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic import markdown_value
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_stage_status
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal_regime_diagnostic"

SIDES = ("up", "down", "both")
REGIME_CONTEXT_MODES = ("router_context", "market_context", "combined", "live_router_context", "live_combined")
CHANGE_FEATURE_SETS = ("auto", "router_context", "market_context", "combined")
MARKET_CONTEXT_PREFIX = "market_"
DEFAULT_MARKET_REGIME_FAMILIES = (
    "volatility_state",
    "temporal_memory_transforms",
    "regime_calendar_state",
    "rejection_chop",
    "liquidity_volume_pressure",
    "structural_room",
)
MARKET_BATCH_METRICS = ("mean", "std", "abs_mean", "q10", "q50", "q90", "finite_rate")

CURRENT_OUTCOME_COLUMNS = {
    "rows",
    "positive_count",
    "negative_count",
    "predicted_positive_count",
    "true_positive_count",
    "false_positive_count",
    "false_negative_count",
    "true_negative_count",
    "precision",
    "recall",
    "false_positive_rate",
    "false_discovery_rate",
    "predicted_positive_rate",
    "base_positive_rate",
    "precision_lift",
    "decision_cost",
    "decision_cost_per_row",
    "decision_cost_per_signal",
    "positive_rate",
    "high_target_window",
    "active_window",
    "captured_high_target_window",
    "missed_high_target_window",
    "high_false_positive_window",
    "offline_topk_precision",
    "offline_topk_recall",
    "prediction_batch_positive_rate",
}

SAFE_NUMERIC_COLUMNS = (
    "candidate_passed_validation",
    "selected_feature_count",
    "threshold",
    "threshold_quantile",
    "max_signals_per_batch",
    "score_mean",
    "score_std",
    "validation_threshold_score",
    "batch_state_gate_probability",
    "batch_state_gate_passed",
    "batch_state_gate_prefix_rows",
    "validation_ranked_signal_quality",
    "validation_precision",
    "validation_precision_lift",
    "validation_false_discovery_rate",
    "validation_predicted_positive_count",
    "validation_active_window_rate",
    "validation_zero_signal_window_rate",
    "validation_batch_count",
    "validation_active_batch_count",
    "validation_lift_positive_batch_rate",
    "validation_median_active_precision_lift",
    "validation_median_active_false_discovery_rate",
    "validation_high_target_window_capture_rate",
    "validation_missed_high_target_window_rate",
    "sequence_feature_count",
    "reliability_score",
    "history_windows",
    "signal_count",
    "active_windows",
    "precision_lift_lcb",
    "precision_lcb",
    "selected_window_row_lift",
    "selected_window_row_lift_lcb",
    "selected_window_false_discovery_rate",
    "past_20_batch_positive_rate_mean",
    "past_20_batch_positive_rate_std",
    "past_60_batch_positive_rate_mean",
    "past_60_batch_positive_rate_std",
    "recent_candidate_precision_lift",
    "recent_candidate_precision_lift_lcb",
    "recent_candidate_window_selection_lift",
    "recent_candidate_selected_window_row_lift",
    "recent_candidate_selected_window_row_lift_lcb",
    "recent_candidate_false_discovery_rate",
    "current_validation_positive_rate",
    "current_validation_signal_rate",
)

# These fields are label-free, but they summarize the current prediction batch
# after it has been scored.  That is useful for diagnostics, but it is not
# available at the first live row of the batch, so strict live replay excludes
# them from regime/change-state inputs.
CURRENT_PREDICTION_BATCH_CONTEXT_COLUMNS = {
    "score_mean",
    "score_std",
    "batch_state_gate_probability",
    "batch_state_gate_passed",
    "batch_state_gate_prefix_rows",
}

LIVE_SAFE_NUMERIC_COLUMNS = tuple(
    col for col in SAFE_NUMERIC_COLUMNS if col not in CURRENT_PREDICTION_BATCH_CONTEXT_COLUMNS
)

CHANGE_FEATURES = (
    "score_mean",
    "score_std",
    "current_validation_positive_rate",
    "current_validation_signal_rate",
    "past_20_batch_positive_rate_mean",
    "past_60_batch_positive_rate_mean",
    "recent_candidate_false_discovery_rate",
)


@dataclass(frozen=True)
class RegimeConfig:
    state_count: int
    pca_components: int
    min_history_windows: int
    lookback_windows: int
    random_seed: int
    model_mode: str


@dataclass(frozen=True)
class ChangeConfig:
    lookback_windows: int
    cusum_z: float
    page_hinkley_delta: float
    page_hinkley_threshold: float
    feature_set: str = "auto"


@dataclass(frozen=True)
class TargetMatchConfig:
    favorable_min_signals: int
    favorable_min_lift: float
    favorable_max_fdr: float
    avoid_min_signals: int
    avoid_max_lift: float
    avoid_min_fdr: float


def main() -> int:
    args = parse_args()
    router_runs = tuple(Path(item) for item in args.router_run)
    if not router_runs:
        raise ValueError("At least one --router-run is required")

    run_root = run_root_for_args()
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal_regime_diagnostic")

    side_filter = parse_sides(args.side)
    candidate_filter = parse_candidate_names(args.candidate_names)
    raw = load_router_runs(router_runs, side_filter=side_filter, candidate_filter=candidate_filter)
    live_context = str(args.regime_context_mode).startswith("live_")
    router_context = safe_regime_context(raw, live_safe=live_context)
    market_context = pl.DataFrame()
    if str(args.regime_context_mode) in {"market_context", "combined"}:
        market_context = build_market_regime_context(
            router_context,
            args=args,
            router_runs=router_runs,
        )
    context = combine_regime_context(
        router_context,
        market_context,
        mode=str(args.regime_context_mode),
    )

    regime = assign_past_only_regimes(
        context,
        config=RegimeConfig(
            state_count=int(args.state_count),
            pca_components=int(args.pca_components),
            min_history_windows=int(args.regime_min_history_windows),
            lookback_windows=int(args.regime_lookback_windows),
            random_seed=int(args.random_seed),
            model_mode=str(args.model_mode),
        ),
    )
    changes = detect_change_events(
        context,
        config=ChangeConfig(
            lookback_windows=int(args.change_lookback_windows),
            cusum_z=float(args.cusum_z),
            page_hinkley_delta=float(args.page_hinkley_delta),
            page_hinkley_threshold=float(args.page_hinkley_threshold),
            feature_set=str(args.change_feature_set),
        ),
    )
    quality = regime_signal_quality(raw, regime)
    state_metrics = state_quality_summary(quality)
    change_flags = change_flags_by_window(changes)
    regime_change_metrics = regime_change_quality_summary(quality, change_flags)
    change_metrics = change_quality_summary(quality, change_flags)
    target_match_config = TargetMatchConfig(
        favorable_min_signals=int(args.target_match_favorable_min_signals),
        favorable_min_lift=float(args.target_match_favorable_min_lift),
        favorable_max_fdr=float(args.target_match_favorable_max_fdr),
        avoid_min_signals=int(args.target_match_avoid_min_signals),
        avoid_max_lift=float(args.target_match_avoid_max_lift),
        avoid_min_fdr=float(args.target_match_avoid_min_fdr),
    )
    regime_target_match = label_target_match(state_metrics, context_type="regime_state", config=target_match_config)
    regime_change_target_match = label_target_match(
        regime_change_metrics,
        context_type="regime_state_change_flag",
        config=target_match_config,
    )
    change_risk_target_match = label_target_match(
        change_metrics,
        context_type="change_flag",
        config=target_match_config,
    )
    suppression_candidates = suppression_candidates_from_matches(
        regime_target_match,
        regime_change_target_match,
        change_risk_target_match,
    )

    write_rows_parquet(run_root / "regime_context.parquet", regime.to_dicts())
    write_rows_parquet(run_root / "market_regime_context.parquet", market_context.to_dicts())
    write_rows_parquet(run_root / "change_point_events.parquet", changes.to_dicts())
    write_rows_parquet(run_root / "regime_signal_quality.parquet", quality.to_dicts())
    write_rows_parquet(run_root / "hmm_state_metrics.parquet", state_metrics.to_dicts())
    write_rows_parquet(run_root / "regime_target_match.parquet", regime_target_match.to_dicts())
    write_rows_parquet(run_root / "regime_change_target_match.parquet", regime_change_target_match.to_dicts())
    write_rows_parquet(run_root / "change_risk_target_match.parquet", change_risk_target_match.to_dicts())
    write_rows_parquet(run_root / "regime_suppression_candidates.parquet", suppression_candidates.to_dicts())
    write_regime_report(
        run_root / "regime_transfer_report.md",
        router_runs=router_runs,
        context=regime,
        changes=changes,
        state_metrics=state_metrics,
        regime_target_match=regime_target_match,
        change_risk_target_match=change_risk_target_match,
        suppression_candidates=suppression_candidates,
    )
    write_json(
        run_root / "regime_diagnostic_config.json",
        {
            "router_runs": [str(path) for path in router_runs],
            "side": str(args.side),
            "candidate_names": sorted(candidate_filter) if candidate_filter else [],
            "regime_context_mode": str(args.regime_context_mode),
            "live_safe_context": bool(live_context),
            "state_count": int(args.state_count),
            "pca_components": int(args.pca_components),
            "regime_min_history_windows": int(args.regime_min_history_windows),
            "regime_lookback_windows": int(args.regime_lookback_windows),
            "model_mode": str(args.model_mode),
            "change_lookback_windows": int(args.change_lookback_windows),
            "change_feature_set": str(args.change_feature_set),
            "cusum_z": float(args.cusum_z),
            "page_hinkley_delta": float(args.page_hinkley_delta),
            "page_hinkley_threshold": float(args.page_hinkley_threshold),
            "market_regime": {
                "asset": str(args.asset or ""),
                "root": str(args.root or ""),
                "config": str(args.config),
                "base_run": str(args.base_run or ""),
                "panel_path": str(args.market_regime_panel_path or ""),
                "families": parse_csv(args.market_regime_families),
                "max_features_per_family": int(args.market_regime_max_features_per_family),
                "lookback_batches": int(args.market_regime_lookback_batches),
                "include_current_batch": bool(args.market_regime_include_current_batch),
                "context_rows": market_context.height,
            },
            "target_match": target_match_config.__dict__,
            "safe_numeric_columns": [col for col in SAFE_NUMERIC_COLUMNS if col in context.columns],
            "live_safe_numeric_columns": [col for col in LIVE_SAFE_NUMERIC_COLUMNS if col in context.columns],
            "excluded_current_prediction_batch_context_columns": sorted(CURRENT_PREDICTION_BATCH_CONTEXT_COLUMNS),
            "market_numeric_columns": sorted(col for col in context.columns if col.startswith(MARKET_CONTEXT_PREFIX)),
            "excluded_current_outcome_columns": sorted(CURRENT_OUTCOME_COLUMNS),
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal_regime_diagnostic",
        status="complete",
        summary=summarize_stage(regime, changes, state_metrics) | {
            "regime_context_mode": str(args.regime_context_mode),
            "market_context_rows": market_context.height,
            "suppression_candidates": suppression_candidates.height,
            "favorable_regime_matches": count_match_status(regime_target_match, "favorable"),
            "avoid_regime_matches": count_match_status(regime_target_match, "avoid"),
        },
    )
    append_event(events_path, "stage_done", run=str(run_root))
    print(f"[rpf-regime] done run={run_root}", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose regime/change-risk transfer for ranked-signal router runs.")
    parser.add_argument("--router-run", action="append", required=True)
    parser.add_argument("--side", choices=SIDES, default="both")
    parser.add_argument("--candidate-names", default="")
    parser.add_argument("--regime-context-mode", choices=REGIME_CONTEXT_MODES, default="router_context")
    parser.add_argument("--asset", default="")
    parser.add_argument("--root", default="")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--base-run", default="")
    parser.add_argument("--market-regime-panel-path", default="")
    parser.add_argument("--market-regime-families", default=",".join(DEFAULT_MARKET_REGIME_FAMILIES))
    parser.add_argument("--market-regime-max-features-per-family", type=int, default=64)
    parser.add_argument("--market-regime-lookback-batches", type=int, default=20)
    parser.add_argument("--market-regime-include-current-batch", action="store_true")
    parser.add_argument("--state-count", type=int, default=3)
    parser.add_argument("--pca-components", type=int, default=5)
    parser.add_argument("--regime-min-history-windows", type=int, default=80)
    parser.add_argument("--regime-lookback-windows", type=int, default=240)
    parser.add_argument("--model-mode", choices=("auto", "hmm", "gmm_markov"), default="auto")
    parser.add_argument("--change-lookback-windows", type=int, default=60)
    parser.add_argument("--change-feature-set", choices=CHANGE_FEATURE_SETS, default="auto")
    parser.add_argument("--cusum-z", type=float, default=3.0)
    parser.add_argument("--page-hinkley-delta", type=float, default=0.01)
    parser.add_argument("--page-hinkley-threshold", type=float, default=3.0)
    parser.add_argument("--target-match-favorable-min-signals", type=int, default=80)
    parser.add_argument("--target-match-favorable-min-lift", type=float, default=1.10)
    parser.add_argument("--target-match-favorable-max-fdr", type=float, default=0.58)
    parser.add_argument("--target-match-avoid-min-signals", type=int, default=80)
    parser.add_argument("--target-match-avoid-max-lift", type=float, default=1.00)
    parser.add_argument("--target-match-avoid-min-fdr", type=float, default=0.60)
    parser.add_argument("--random-seed", type=int, default=17)
    return parser.parse_args()


def parse_sides(value: str) -> set[str]:
    side = str(value)
    if side == "both":
        return {"up", "down"}
    return {side}


def parse_candidate_names(value: str | None) -> set[str]:
    return {part.strip() for part in str(value or "").split(",") if part.strip()}


def parse_csv(value: str | None) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def first_router_config(router_runs: tuple[Path, ...]) -> dict[str, Any]:
    for run in router_runs:
        path = run / "router_config.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
    return {}


def combine_regime_context(router_context: pl.DataFrame, market_context: pl.DataFrame, *, mode: str) -> pl.DataFrame:
    live_safe = str(mode).startswith("live_")
    normalized_mode = str(mode).removeprefix("live_")
    if normalized_mode == "router_context" or market_context.is_empty():
        return router_context
    join_keys = [col for col in ("source_idx", "pred_batch_id") if col in router_context.columns and col in market_context.columns]
    if not join_keys:
        raise ValueError("Cannot attach market context: missing source_idx/pred_batch_id join keys")
    joined = router_context.join(market_context, on=join_keys, how="left")
    if normalized_mode == "combined":
        return safe_regime_context(joined, live_safe=live_safe)
    if normalized_mode == "market_context":
        identity = [
            col
            for col in (
                "source_run",
                "source_idx",
                "window_end_offset_steps",
                "outer_window_count",
                "selection_mode",
                "candidate_set",
                "side",
                "candidate_name",
                "step_idx",
                "pred_batch_id",
            )
            if col in joined.columns
        ]
        market_cols = sorted(col for col in joined.columns if col.startswith(MARKET_CONTEXT_PREFIX))
        return joined.select(list(dict.fromkeys([*identity, *market_cols])))
    raise ValueError(f"Unsupported regime context mode: {mode}")


def build_market_regime_context(
    router_context: pl.DataFrame,
    *,
    args: argparse.Namespace,
    router_runs: tuple[Path, ...],
) -> pl.DataFrame:
    if router_context.is_empty():
        return pl.DataFrame()
    clean_config = load_clean_config(Path(args.config))
    router_config = first_router_config(router_runs)
    asset = str(args.asset or router_config.get("asset") or clean_config.asset)
    root = str(args.root or router_config.get("root") or clean_config.root)
    context = resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=clean_config.target_col)
    family_columns = market_feature_columns(
        context.manifest.feature_columns,
        panel_path=str(args.market_regime_panel_path or ""),
        families=parse_csv(args.market_regime_families),
        max_features_per_family=int(args.market_regime_max_features_per_family),
    )
    if not any(family_columns.values()):
        raise ValueError("Market regime context selected zero RPF features")

    available_ids = ordered_available_batch_ids(context, Path(args.base_run) if args.base_run else None)
    pred_rows = (
        router_context.select([col for col in ("source_idx", "pred_batch_id") if col in router_context.columns])
        .unique()
        .sort(["source_idx", "pred_batch_id"])
        .to_dicts()
    )
    lookback = int(args.market_regime_lookback_batches)
    include_current = bool(args.market_regime_include_current_batch)
    needed: set[int] = set()
    histories: dict[tuple[int, int], list[int]] = {}
    for row in pred_rows:
        pred_batch_id = int(row["pred_batch_id"])
        history = prior_available_batches(
            available_ids,
            pred_batch_id,
            lookback=lookback,
            include_current=include_current,
        )
        histories[(int(row.get("source_idx", 0)), pred_batch_id)] = history
        needed.update(history)

    per_batch = compute_market_batch_stats(
        feature_root=context.feature_root,
        batch_ids=tuple(sorted(needed)),
        family_columns=family_columns,
    )
    rows: list[dict[str, Any]] = []
    for row in pred_rows:
        source_idx = int(row.get("source_idx", 0))
        pred_batch_id = int(row["pred_batch_id"])
        history = histories.get((source_idx, pred_batch_id), [])
        payload: dict[str, Any] = {
            "source_idx": source_idx,
            "pred_batch_id": pred_batch_id,
            "market_context_lookback_batches": int(lookback),
            "market_context_include_current_batch": bool(include_current),
            "market_context_history_batch_count": int(len(history)),
            "market_context_last_batch_id": int(history[-1]) if history else None,
        }
        payload.update(aggregate_market_history(history, per_batch, family_columns))
        rows.append(payload)
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def ordered_available_batch_ids(context: Any, base_run: Path | None) -> tuple[int, ...]:
    if base_run:
        path = base_run / "batch_index.parquet"
        if path.exists():
            frame = pl.read_parquet(path)
            if "batch_id" in frame.columns:
                return tuple(int(value) for value in frame["batch_id"].to_list())
    return available_batch_ids(context.feature_root, context.label_root)


def prior_available_batches(
    available_ids: tuple[int, ...],
    pred_batch_id: int,
    *,
    lookback: int,
    include_current: bool,
) -> list[int]:
    if lookback <= 0:
        return []
    end = bisect.bisect_right(available_ids, int(pred_batch_id)) if include_current else bisect.bisect_left(available_ids, int(pred_batch_id))
    start = max(0, end - int(lookback))
    return [int(value) for value in available_ids[start:end]]


def market_feature_columns(
    manifest_features: tuple[str, ...],
    *,
    panel_path: str,
    families: list[str],
    max_features_per_family: int,
) -> dict[str, tuple[str, ...]]:
    allowed = tuple(load_panel_features(panel_path, manifest_features)) if panel_path else tuple(manifest_features)
    allowed_set = set(allowed)
    selected: dict[str, tuple[str, ...]] = {}
    for family in families:
        if family not in FAMILY_PREFIXES:
            known = ", ".join(sorted(FAMILY_PREFIXES))
            raise ValueError(f"Unknown market regime family {family!r}; expected one of: {known}")
        prefixes = FAMILY_PREFIXES[family]
        cols = [feature for feature in manifest_features if feature in allowed_set and feature.startswith(prefixes)]
        if max_features_per_family > 0:
            cols = cols[: int(max_features_per_family)]
        selected[family] = tuple(cols)
    return selected


def compute_market_batch_stats(
    *,
    feature_root: Path,
    batch_ids: tuple[int, ...],
    family_columns: dict[str, tuple[str, ...]],
) -> dict[int, dict[str, float | int | None]]:
    all_columns = tuple(dict.fromkeys(col for cols in family_columns.values() for col in cols))
    out: dict[int, dict[str, float | int | None]] = {}
    if not all_columns:
        return out
    for batch_id in batch_ids:
        path = feature_root / f"batch_{int(batch_id):04d}.parquet"
        if not path.exists():
            continue
        schema = set(pl.read_parquet_schema(path))
        present = [col for col in all_columns if col in schema]
        if not present:
            continue
        frame = pl.read_parquet(path, columns=present)
        row: dict[str, float | int | None] = {"batch_id": int(batch_id)}
        for family, columns in family_columns.items():
            present_family_cols = [col for col in columns if col in frame.columns]
            row.update(family_batch_stats(family, frame, present_family_cols))
        out[int(batch_id)] = row
    return out


def family_batch_stats(family: str, frame: pl.DataFrame, columns: list[str]) -> dict[str, float | int | None]:
    prefix = f"{MARKET_CONTEXT_PREFIX}{family}"
    out: dict[str, float | int | None] = {
        f"{prefix}_feature_count": int(len(columns)),
        f"{prefix}_row_count": int(frame.height),
    }
    if not columns or frame.is_empty():
        for metric in MARKET_BATCH_METRICS:
            out[f"{prefix}_{metric}"] = None
        return out
    values = frame.select(columns).to_numpy().astype("float64", copy=False)
    finite_mask = np.isfinite(values)
    finite_values = values[finite_mask]
    total_cells = int(values.size)
    out[f"{prefix}_finite_rate"] = float(finite_values.size / total_cells) if total_cells else None
    if finite_values.size == 0:
        for metric in ("mean", "std", "abs_mean", "q10", "q50", "q90"):
            out[f"{prefix}_{metric}"] = None
        return out
    out[f"{prefix}_mean"] = float(np.mean(finite_values))
    out[f"{prefix}_std"] = float(np.std(finite_values))
    out[f"{prefix}_abs_mean"] = float(np.mean(np.abs(finite_values)))
    out[f"{prefix}_q10"] = float(np.quantile(finite_values, 0.10))
    out[f"{prefix}_q50"] = float(np.quantile(finite_values, 0.50))
    out[f"{prefix}_q90"] = float(np.quantile(finite_values, 0.90))
    return out


def aggregate_market_history(
    history: list[int],
    per_batch: dict[int, dict[str, float | int | None]],
    family_columns: dict[str, tuple[str, ...]],
) -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {}
    for family, columns in family_columns.items():
        prefix = f"{MARKET_CONTEXT_PREFIX}{family}"
        rows = [per_batch[batch_id] for batch_id in history if batch_id in per_batch]
        out[f"{prefix}_batch_count"] = int(len(rows))
        out[f"{prefix}_feature_count"] = int(len(columns))
        for metric in MARKET_BATCH_METRICS:
            values = numeric_values(row.get(f"{prefix}_{metric}") for row in rows)
            last = values[-1] if values else None
            mean = float(np.mean(values)) if values else None
            std = float(np.std(values)) if values else None
            out[f"{prefix}_{metric}_last"] = last
            out[f"{prefix}_{metric}_lookback_mean"] = mean
            out[f"{prefix}_{metric}_lookback_std"] = std
            if last is not None and mean is not None and std is not None and std > 1e-12:
                out[f"{prefix}_{metric}_last_z"] = float((last - mean) / std)
            else:
                out[f"{prefix}_{metric}_last_z"] = None
    return out


def numeric_values(values: Any) -> list[float]:
    out: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            out.append(number)
    return out


def load_router_runs(
    router_runs: tuple[Path, ...],
    *,
    side_filter: set[str],
    candidate_filter: set[str],
) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for source_idx, run in enumerate(sort_router_runs_chronologically(router_runs)):
        frame = load_router_run(run, source_idx=source_idx)
        if side_filter:
            frame = frame.filter(pl.col("side").is_in(sorted(side_filter)))
        if candidate_filter:
            frame = frame.filter(pl.col("candidate_name").is_in(sorted(candidate_filter)))
        if not frame.is_empty():
            frames.append(frame)
    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


def sort_router_runs_chronologically(router_runs: tuple[Path, ...]) -> list[Path]:
    """Return older router blocks first, independent of CLI argument order.

    ``window_end_offset_steps`` is larger for older slices because offset 0 is
    the latest selected window block.  Regime fitting uses previous rows as
    history, so chronological order matters.
    """

    keyed: list[tuple[int, str, Path]] = []
    for run in router_runs:
        config_path = run / "router_config.json"
        if not config_path.exists():
            keyed.append((0, str(run), run))
            continue
        try:
            config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            keyed.append((0, str(run), run))
            continue
        keyed.append((int(config.get("window_end_offset_steps", 0)), str(run), run))
    return [run for _, _, run in sorted(keyed, key=lambda item: (-item[0], item[1]))]


def load_router_run(run: Path, *, source_idx: int) -> pl.DataFrame:
    if not run.exists():
        raise FileNotFoundError(f"Router run does not exist: {run}")
    prediction_path = run / "candidate_prediction_window_metrics.parquet"
    validation_path = run / "candidate_validation_metrics.parquet"
    reliability_path = run / "candidate_reliability_state.parquet"
    batch_regime_path = run / "batch_regime_diagnostics.parquet"
    config_path = run / "router_config.json"
    if not prediction_path.exists():
        raise FileNotFoundError(f"Missing required artifact: {prediction_path}")

    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    prediction = pl.read_parquet(prediction_path).with_columns(
        pl.lit(str(run)).alias("source_run"),
        pl.lit(int(source_idx)).alias("source_idx"),
        pl.lit(int(config.get("window_end_offset_steps", 0))).alias("window_end_offset_steps"),
        pl.lit(int(config.get("outer_window_count", 0))).alias("outer_window_count"),
        pl.lit(str(config.get("selection_mode", ""))).alias("selection_mode"),
        pl.lit(str(config.get("candidate_set", ""))).alias("candidate_set"),
    )

    out = prediction
    if validation_path.exists():
        validation = pl.read_parquet(validation_path).select(
            [col for col in pl.read_parquet(validation_path).columns if col not in {"diagnostic", "status"}]
        )
        out = out.join(validation, on=["side", "candidate_name", "step_idx", "pred_batch_id"], how="left", suffix="_validation")

    if reliability_path.exists():
        reliability = (
            pl.read_parquet(reliability_path)
            .rename({"router_step_idx": "step_idx", "router_pred_batch_id": "pred_batch_id"})
            .select(
                [
                    col
                    for col in pl.read_parquet(reliability_path)
                    .rename({"router_step_idx": "step_idx", "router_pred_batch_id": "pred_batch_id"})
                    .columns
                    if col not in {"diagnostic"}
                ]
            )
        )
        out = out.join(reliability, on=["side", "candidate_name", "step_idx", "pred_batch_id"], how="left", suffix="_reliability")

    if batch_regime_path.exists():
        batch_regime = pl.read_parquet(batch_regime_path).rename({"pred_batch_id": "batch_regime_pred_batch_id"})
        out = out.join(
            batch_regime,
            left_on=["side", "pred_batch_id"],
            right_on=["side", "batch_regime_pred_batch_id"],
            how="left",
            suffix="_batch_regime",
        )

    return out.sort(["source_idx", "side", "candidate_name", "pred_batch_id"])


def safe_regime_context(df: pl.DataFrame, *, live_safe: bool = False) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame()
    required = [
        "source_run",
        "source_idx",
        "window_end_offset_steps",
        "outer_window_count",
        "selection_mode",
        "candidate_set",
        "side",
        "candidate_name",
        "step_idx",
        "pred_batch_id",
    ]
    keep = [col for col in required if col in df.columns]
    numeric_columns = LIVE_SAFE_NUMERIC_COLUMNS if live_safe else SAFE_NUMERIC_COLUMNS
    for col in numeric_columns:
        if col in df.columns and col not in CURRENT_OUTCOME_COLUMNS:
            keep.append(col)
    for col in df.columns:
        if col.startswith(MARKET_CONTEXT_PREFIX) and col not in CURRENT_OUTCOME_COLUMNS:
            keep.append(col)
    out = df.select(list(dict.fromkeys(keep)))
    leaked = CURRENT_OUTCOME_COLUMNS & set(out.columns)
    if leaked:
        raise ValueError(f"Regime context contains current prediction outcome columns: {sorted(leaked)}")
    if live_safe:
        leaked_prediction_context = CURRENT_PREDICTION_BATCH_CONTEXT_COLUMNS & set(out.columns)
        if leaked_prediction_context:
            raise ValueError(
                "Live regime context contains current prediction-batch context columns: "
                f"{sorted(leaked_prediction_context)}"
            )
    return out.sort([col for col in ["source_idx", "side", "candidate_name", "pred_batch_id"] if col in out.columns])


def assign_past_only_regimes(df: pl.DataFrame, *, config: RegimeConfig) -> pl.DataFrame:
    if df.is_empty():
        return df
    feature_cols = usable_feature_columns(df)
    rows: list[dict[str, Any]] = []
    for key, group in df.group_by(["side", "candidate_name"], maintain_order=True):
        group_rows = group.sort(["source_idx", "pred_batch_id"]).to_dicts()
        history: list[dict[str, Any]] = []
        previous_state: int | None = None
        for row in group_rows:
            payload = dict(row)
            if len(history) < config.min_history_windows or not feature_cols:
                payload.update(empty_regime_fields("insufficient_history" if feature_cols else "no_safe_numeric_features"))
            else:
                train_rows = history[-config.lookback_windows :] if config.lookback_windows > 0 else history
                assignment = fit_predict_regime_state(train_rows, row, feature_cols, config, previous_state=previous_state)
                payload.update(assignment)
                if assignment.get("regime_state") is not None:
                    previous_state = int(assignment["regime_state"])
            rows.append(payload)
            history.append(row)
    return pl.DataFrame(rows, infer_schema_length=None) if rows else df


def usable_feature_columns(df: pl.DataFrame) -> list[str]:
    cols: list[str] = []
    candidates = [*SAFE_NUMERIC_COLUMNS, *sorted(col for col in df.columns if col.startswith(MARKET_CONTEXT_PREFIX))]
    for col in candidates:
        if col not in df.columns:
            continue
        values = df[col].cast(pl.Float64, strict=False).to_numpy()
        finite = values[np.isfinite(values)]
        if finite.size and float(np.nanstd(finite)) > 1e-12:
            cols.append(col)
    return cols


def fit_predict_regime_state(
    train_rows: list[dict[str, Any]],
    current_row: dict[str, Any],
    feature_cols: list[str],
    config: RegimeConfig,
    *,
    previous_state: int | None,
) -> dict[str, Any]:
    x_train = rows_to_matrix(train_rows, feature_cols)
    x_current = rows_to_matrix([current_row], feature_cols)
    x_train, x_current = keep_informative_columns(x_train, x_current)
    if x_train.shape[1] == 0:
        return empty_regime_fields("no_informative_safe_numeric_features")
    if x_train.shape[0] < max(config.state_count * 5, 20):
        return empty_regime_fields("insufficient_fit_rows")

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_current_scaled = scaler.transform(x_current)
    pca_dim = min(config.pca_components, x_train_scaled.shape[1], max(1, x_train_scaled.shape[0] - 1))
    if pca_dim < x_train_scaled.shape[1]:
        pca = PCA(n_components=pca_dim, random_state=config.random_seed)
        x_train_model = pca.fit_transform(x_train_scaled)
        x_current_model = pca.transform(x_current_scaled)
    else:
        x_train_model = x_train_scaled
        x_current_model = x_current_scaled

    if config.model_mode in {"auto", "hmm"}:
        hmm_result = try_hmm_state(x_train_model, x_current_model, config, previous_state=previous_state)
        if hmm_result is not None:
            return hmm_result
        if config.model_mode == "hmm":
            return empty_regime_fields("hmmlearn_unavailable_or_failed")

    gmm = GaussianMixture(
        n_components=config.state_count,
        covariance_type="diag",
        random_state=config.random_seed,
        reg_covar=1e-6,
        n_init=3,
    )
    gmm.fit(x_train_model)
    train_states = gmm.predict(x_train_model)
    posterior = gmm.predict_proba(x_current_model)[0]
    state = int(np.argmax(posterior))
    return regime_payload(
        model="gmm_markov_proxy",
        state=state,
        posterior=posterior,
        train_states=train_states,
        previous_state=previous_state,
    )


def try_hmm_state(
    x_train: np.ndarray,
    x_current: np.ndarray,
    config: RegimeConfig,
    *,
    previous_state: int | None,
) -> dict[str, Any] | None:
    try:
        from hmmlearn.hmm import GaussianHMM  # type: ignore
    except Exception:
        return None
    try:
        model = GaussianHMM(
            n_components=config.state_count,
            covariance_type="diag",
            n_iter=100,
            random_state=config.random_seed,
            min_covar=1e-6,
        )
        model.fit(x_train)
        train_states = model.predict(x_train)
        posterior = model.predict_proba(np.vstack([x_train[-1:], x_current]))[-1]
        state = int(np.argmax(posterior))
        return regime_payload(
            model="gaussian_hmm",
            state=state,
            posterior=posterior,
            train_states=train_states,
            previous_state=previous_state,
        )
    except Exception:
        return None


def regime_payload(
    *,
    model: str,
    state: int,
    posterior: np.ndarray,
    train_states: np.ndarray,
    previous_state: int | None,
) -> dict[str, Any]:
    posterior = np.asarray(posterior, dtype=float)
    max_prob = float(np.nanmax(posterior)) if posterior.size else None
    entropy = posterior_entropy(posterior)
    transition = transition_summary(train_states, previous_state, state)
    out: dict[str, Any] = {
        "regime_model": model,
        "regime_status": "ok",
        "regime_state": state,
        "regime_posterior_max": max_prob,
        "regime_entropy": entropy,
        "regime_changed_from_previous": previous_state is not None and int(previous_state) != int(state),
        "regime_transition_probability": transition["probability"],
        "regime_transition_count": transition["count"],
        "regime_train_state_count": int(len(set(int(v) for v in train_states))),
    }
    for idx, value in enumerate(posterior):
        out[f"regime_posterior_state_{idx}"] = float(value)
    return out


def transition_summary(train_states: np.ndarray, previous_state: int | None, current_state: int) -> dict[str, Any]:
    if previous_state is None or train_states.size < 2:
        return {"probability": None, "count": 0}
    total = 0
    count = 0
    for left, right in zip(train_states[:-1], train_states[1:]):
        if int(left) == int(previous_state):
            total += 1
            if int(right) == int(current_state):
                count += 1
    return {"probability": float(count / total) if total else None, "count": int(count)}


def posterior_entropy(posterior: np.ndarray) -> float | None:
    finite = posterior[np.isfinite(posterior) & (posterior > 0)]
    if finite.size == 0:
        return None
    return float(-(finite * np.log(finite)).sum())


def empty_regime_fields(status: str) -> dict[str, Any]:
    return {
        "regime_model": None,
        "regime_status": status,
        "regime_state": None,
        "regime_posterior_max": None,
        "regime_entropy": None,
        "regime_changed_from_previous": None,
        "regime_transition_probability": None,
        "regime_transition_count": None,
        "regime_train_state_count": None,
    }


def rows_to_matrix(rows: list[dict[str, Any]], feature_cols: list[str]) -> np.ndarray:
    matrix = np.array([[to_float(row.get(col)) for col in feature_cols] for row in rows], dtype=float)
    if matrix.size == 0:
        return matrix.reshape((len(rows), 0))
    finite = np.where(np.isfinite(matrix), matrix, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        med = np.nanmedian(finite, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    inds = np.where(~np.isfinite(matrix))
    if inds[0].size:
        matrix[inds] = med[inds[1]]
    return matrix


def keep_informative_columns(x_train: np.ndarray, x_current: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if x_train.size == 0 or x_train.shape[1] == 0:
        return x_train, x_current
    std = np.nanstd(x_train, axis=0)
    keep = np.isfinite(std) & (std > 1e-12)
    if not np.any(keep):
        return x_train[:, :0], x_current[:, :0]
    return x_train[:, keep], x_current[:, keep]


def detect_change_events(df: pl.DataFrame, *, config: ChangeConfig) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame()
    rows: list[dict[str, Any]] = []
    for key, group in df.group_by(["side", "candidate_name"], maintain_order=True):
        group_rows = group.sort(["source_idx", "pred_batch_id"]).to_dicts()
        feature_columns = change_feature_columns(group, config.feature_set)
        ph_state = {feature: {"mean": 0.0, "count": 0, "cum": 0.0, "min_cum": 0.0} for feature in feature_columns}
        history: list[dict[str, Any]] = []
        for row in group_rows:
            for feature in feature_columns:
                if feature not in row:
                    continue
                value = to_float(row.get(feature))
                if value is None:
                    continue
                prior = history[-config.lookback_windows :] if config.lookback_windows > 0 else history
                prior_values = np.array([to_float(item.get(feature)) for item in prior], dtype=object)
                prior_values = np.array([float(item) for item in prior_values if item is not None and np.isfinite(float(item))])
                if prior_values.size >= max(10, min(config.lookback_windows, 20)):
                    mean = float(prior_values.mean())
                    std = float(prior_values.std()) or 1e-12
                    z = float((value - mean) / std)
                    cusum_alarm = bool(abs(z) >= float(config.cusum_z))
                else:
                    mean = None
                    std = None
                    z = None
                    cusum_alarm = False
                ph_alarm = page_hinkley_update(ph_state[feature], value, config)
                if cusum_alarm or ph_alarm:
                    rows.append(
                        {
                            "source_run": row.get("source_run"),
                            "source_idx": row.get("source_idx"),
                            "side": row.get("side"),
                            "candidate_name": row.get("candidate_name"),
                            "step_idx": row.get("step_idx"),
                            "pred_batch_id": row.get("pred_batch_id"),
                            "feature": feature,
                            "value": value,
                            "prior_mean": mean,
                            "prior_std": std,
                            "zscore": z,
                            "cusum_alarm": cusum_alarm,
                            "page_hinkley_alarm": ph_alarm,
                            "change_alarm": True,
                        }
                    )
            history.append(row)
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def change_feature_columns(df: pl.DataFrame, feature_set: str) -> list[str]:
    router_features = [feature for feature in CHANGE_FEATURES if feature in df.columns]
    market_features = [
        col
        for col in sorted(df.columns)
        if col.startswith(MARKET_CONTEXT_PREFIX) and (col.endswith("_last_z") or col.endswith("_lookback_mean"))
    ]
    if feature_set == "router_context":
        return router_features
    if feature_set == "market_context":
        return market_features
    if feature_set == "combined":
        return [*router_features, *market_features]
    if feature_set == "auto":
        return [*router_features, *market_features] if market_features else router_features
    raise ValueError(f"Unsupported change feature set: {feature_set}")


def page_hinkley_update(state: dict[str, float], value: float, config: ChangeConfig) -> bool:
    state["count"] += 1
    count = state["count"]
    state["mean"] += (value - state["mean"]) / count
    state["cum"] += value - state["mean"] - float(config.page_hinkley_delta)
    state["min_cum"] = min(state["min_cum"], state["cum"])
    alarm = bool((state["cum"] - state["min_cum"]) > float(config.page_hinkley_threshold))
    if alarm:
        state["cum"] = 0.0
        state["min_cum"] = 0.0
    return alarm


def regime_signal_quality(raw: pl.DataFrame, regime: pl.DataFrame) -> pl.DataFrame:
    if raw.is_empty() or regime.is_empty():
        return pl.DataFrame()
    join_keys = [col for col in ["source_run", "side", "candidate_name", "step_idx", "pred_batch_id"] if col in raw.columns and col in regime.columns]
    state_cols = [
        col
        for col in [
            "source_run",
            "side",
            "candidate_name",
            "step_idx",
            "pred_batch_id",
            "regime_model",
            "regime_status",
            "regime_state",
            "regime_posterior_max",
            "regime_entropy",
            "regime_changed_from_previous",
            "regime_transition_probability",
        ]
        if col in regime.columns
    ]
    outcome_cols = [
        col
        for col in [
            "source_run",
            "side",
            "candidate_name",
            "step_idx",
            "pred_batch_id",
            "rows",
            "positive_count",
            "predicted_positive_count",
            "true_positive_count",
            "false_positive_count",
            "precision",
            "false_discovery_rate",
            "base_positive_rate",
            "precision_lift",
            "positive_rate",
            "active_window",
            "high_false_positive_window",
        ]
        if col in raw.columns
    ]
    out = raw.select(outcome_cols).join(regime.select(state_cols), on=join_keys, how="left")
    return out


def state_quality_summary(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty() or "regime_state" not in df.columns:
        return pl.DataFrame()
    state_df = df.filter(pl.col("regime_status") == "ok")
    if state_df.is_empty():
        return pl.DataFrame()
    grouped = (
        state_df.group_by(["side", "candidate_name", "regime_model", "regime_state"])
        .agg(
            pl.len().alias("windows"),
            pl.col("predicted_positive_count").fill_null(0).sum().alias("signals"),
            pl.col("true_positive_count").fill_null(0).sum().alias("true_positives"),
            pl.col("false_positive_count").fill_null(0).sum().alias("false_positives"),
            pl.col("positive_count").fill_null(0).sum().alias("positives"),
            pl.col("rows").fill_null(0).sum().alias("rows"),
            pl.col("regime_posterior_max").mean().alias("posterior_max_mean"),
            pl.col("regime_entropy").mean().alias("entropy_mean"),
        )
        .with_columns(
            (pl.col("signals") > 0).alias("has_signals"),
            (pl.col("true_positives") / pl.col("signals")).alias("precision"),
            (pl.col("false_positives") / pl.col("signals")).alias("false_discovery_rate"),
            (pl.col("positives") / pl.col("rows")).alias("base_rate"),
            ((pl.col("true_positives") / pl.col("signals")) / (pl.col("positives") / pl.col("rows"))).alias(
                "precision_lift"
            ),
        )
        .sort(["side", "candidate_name", "regime_state"])
    )
    return grouped


def change_flags_by_window(changes: pl.DataFrame) -> pl.DataFrame:
    if changes.is_empty():
        return pl.DataFrame()
    return (
        changes.group_by(["source_run", "side", "candidate_name", "step_idx", "pred_batch_id"])
        .agg(
            pl.len().alias("change_event_count"),
            pl.col("cusum_alarm").sum().alias("cusum_count"),
            pl.col("page_hinkley_alarm").sum().alias("page_hinkley_count"),
        )
        .with_columns(
            (pl.col("change_event_count") > 0).alias("has_any_change"),
            (pl.col("cusum_count") > 0).alias("has_cusum"),
            (pl.col("page_hinkley_count") > 0).alias("has_page_hinkley"),
        )
    )


def regime_change_quality_summary(quality: pl.DataFrame, change_flags: pl.DataFrame) -> pl.DataFrame:
    if quality.is_empty() or "regime_state" not in quality.columns:
        return pl.DataFrame()
    joined = quality_with_change_flags(quality, change_flags).filter(pl.col("regime_status") == "ok")
    if joined.is_empty():
        return pl.DataFrame()
    rows: list[pl.DataFrame] = []
    for flag in ("has_any_change", "has_cusum", "has_page_hinkley"):
        summary = aggregate_quality(
            joined,
            group_cols=["side", "candidate_name", "regime_model", "regime_state", flag],
        )
        if not summary.is_empty():
            summary = summary.rename({flag: "change_flag_value"}).with_columns(pl.lit(flag).alias("change_flag"))
            rows.append(summary)
    return pl.concat(rows, how="diagonal_relaxed") if rows else pl.DataFrame()


def change_quality_summary(quality: pl.DataFrame, change_flags: pl.DataFrame) -> pl.DataFrame:
    if quality.is_empty():
        return pl.DataFrame()
    joined = quality_with_change_flags(quality, change_flags)
    rows: list[pl.DataFrame] = []
    for flag in ("has_any_change", "has_cusum", "has_page_hinkley"):
        summary = aggregate_quality(joined, group_cols=["side", "candidate_name", flag])
        if not summary.is_empty():
            summary = summary.rename({flag: "change_flag_value"}).with_columns(pl.lit(flag).alias("change_flag"))
            rows.append(summary)
    return pl.concat(rows, how="diagonal_relaxed") if rows else pl.DataFrame()


def quality_with_change_flags(quality: pl.DataFrame, change_flags: pl.DataFrame) -> pl.DataFrame:
    if change_flags.is_empty():
        return quality.with_columns(
            pl.lit(0).alias("change_event_count"),
            pl.lit(0).alias("cusum_count"),
            pl.lit(0).alias("page_hinkley_count"),
            pl.lit(False).alias("has_any_change"),
            pl.lit(False).alias("has_cusum"),
            pl.lit(False).alias("has_page_hinkley"),
        )
    join_keys = [
        col
        for col in ["source_run", "side", "candidate_name", "step_idx", "pred_batch_id"]
        if col in quality.columns and col in change_flags.columns
    ]
    return (
        quality.join(change_flags, on=join_keys, how="left")
        .with_columns(
            pl.col("change_event_count").fill_null(0),
            pl.col("cusum_count").fill_null(0),
            pl.col("page_hinkley_count").fill_null(0),
            pl.col("has_any_change").fill_null(False),
            pl.col("has_cusum").fill_null(False),
            pl.col("has_page_hinkley").fill_null(False),
        )
    )


def aggregate_quality(df: pl.DataFrame, *, group_cols: list[str]) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame()
    grouped = (
        df.group_by(group_cols)
        .agg(
            pl.len().alias("windows"),
            pl.col("predicted_positive_count").fill_null(0).sum().alias("signals"),
            pl.col("true_positive_count").fill_null(0).sum().alias("true_positives"),
            pl.col("false_positive_count").fill_null(0).sum().alias("false_positives"),
            pl.col("positive_count").fill_null(0).sum().alias("positives"),
            pl.col("rows").fill_null(0).sum().alias("rows"),
        )
        .with_columns(
            (pl.col("signals") > 0).alias("has_signals"),
            (pl.col("true_positives") / pl.col("signals")).alias("precision"),
            (pl.col("false_positives") / pl.col("signals")).alias("false_discovery_rate"),
            (pl.col("positives") / pl.col("rows")).alias("base_rate"),
            ((pl.col("true_positives") / pl.col("signals")) / (pl.col("positives") / pl.col("rows"))).alias(
                "precision_lift"
            ),
        )
    )
    return grouped.sort([col for col in group_cols if col in grouped.columns])


def label_target_match(df: pl.DataFrame, *, context_type: str, config: TargetMatchConfig) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame()
    out = df.with_columns(pl.lit(context_type).alias("context_type"))
    favorable = (
        (pl.col("signals").fill_null(0) >= int(config.favorable_min_signals))
        & (pl.col("precision_lift").fill_null(0.0) >= float(config.favorable_min_lift))
        & (pl.col("false_discovery_rate").fill_null(1.0) <= float(config.favorable_max_fdr))
    )
    avoid = (
        (pl.col("signals").fill_null(0) >= int(config.avoid_min_signals))
        & (
            (pl.col("precision_lift").fill_null(0.0) < float(config.avoid_max_lift))
            | (pl.col("false_discovery_rate").fill_null(1.0) >= float(config.avoid_min_fdr))
        )
    )
    return out.with_columns(
        pl.when(favorable)
        .then(pl.lit("favorable"))
        .when(avoid)
        .then(pl.lit("avoid"))
        .otherwise(pl.lit("neutral"))
        .alias("target_match_status"),
        (
            (pl.col("precision_lift").fill_null(0.0) - 1.0)
            + (0.60 - pl.col("false_discovery_rate").fill_null(1.0))
        ).alias("target_match_score"),
    ).sort(["side", "candidate_name", "target_match_status", "target_match_score"], descending=[False, False, False, True])


def suppression_candidates_from_matches(*frames: pl.DataFrame) -> pl.DataFrame:
    usable = [frame for frame in frames if not frame.is_empty()]
    if not usable:
        return pl.DataFrame()
    combined = pl.concat(usable, how="diagonal_relaxed")
    avoid = combined.filter(pl.col("target_match_status") == "avoid")
    if avoid.is_empty():
        return pl.DataFrame()
    for col in ("regime_state", "change_flag", "change_flag_value"):
        if col not in avoid.columns:
            avoid = avoid.with_columns(pl.lit(None).alias(col))
    return avoid.with_columns(
        pl.concat_str(
            [
                pl.col("context_type").cast(pl.Utf8),
                pl.lit(":"),
                pl.col("regime_state").cast(pl.Utf8).fill_null(""),
                pl.lit(":"),
                pl.col("change_flag").cast(pl.Utf8).fill_null(""),
                pl.lit("="),
                pl.col("change_flag_value").cast(pl.Utf8).fill_null(""),
            ]
        ).alias("suppression_context"),
        (
            pl.when((1.0 - pl.col("precision_lift").fill_null(0.0)) > 0.0)
            .then(1.0 - pl.col("precision_lift").fill_null(0.0))
            .otherwise(0.0)
            + pl.when((pl.col("false_discovery_rate").fill_null(0.0) - 0.60) > 0.0)
            .then(pl.col("false_discovery_rate").fill_null(0.0) - 0.60)
            .otherwise(0.0)
        ).alias("suppression_score"),
    ).sort(["side", "candidate_name", "suppression_score"], descending=[False, False, True])


def count_match_status(df: pl.DataFrame, status: str) -> int:
    if df.is_empty() or "target_match_status" not in df.columns:
        return 0
    return int(df.filter(pl.col("target_match_status") == status).height)


def write_regime_report(
    path: Path,
    *,
    router_runs: tuple[Path, ...],
    context: pl.DataFrame,
    changes: pl.DataFrame,
    state_metrics: pl.DataFrame,
    regime_target_match: pl.DataFrame,
    change_risk_target_match: pl.DataFrame,
    suppression_candidates: pl.DataFrame,
) -> None:
    lines = [
        "# RPF Ranked Signal Regime Diagnostic",
        "",
        "## Purpose",
        "",
        "Diagnose whether ranked-signal quality is conditional on prediction-safe latent regimes and change-risk alarms.",
        "",
        "## Inputs",
        "",
    ]
    lines.extend([f"- `{run}`" for run in router_runs])
    lines.extend(
        [
            "",
            "## Artifact Contract",
            "",
            "- `regime_context.parquet` contains prediction-time-safe context and past-only regime assignments.",
            "- `regime_signal_quality.parquet` joins matured outcomes for analysis only.",
            "- `change_point_events.parquet` contains CUSUM/Page-Hinkley style change alarms from safe context features.",
            "- `hmm_state_metrics.parquet` summarizes signal quality by inferred state.",
            "- `regime_target_match.parquet` labels states as favorable/neutral/avoid for each target side.",
            "- `change_risk_target_match.parquet` labels change-risk flags by side.",
            "- `regime_suppression_candidates.parquet` lists contexts that should be tested as false-positive suppressors.",
            "",
            "## Summary",
            "",
            f"- context rows: `{context.height}`",
            f"- change alarms: `{changes.height}`",
            f"- state metric rows: `{state_metrics.height}`",
            f"- suppression candidates: `{suppression_candidates.height}`",
            "",
            "## State Quality",
            "",
            "| Side | Candidate | Model | State | Windows | Signals | TP | FP | Precision | Base | Lift | FDR |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in state_metrics.to_dicts():
        lines.append(
            "| {side} | {candidate_name} | {regime_model} | {regime_state} | {windows} | {signals} | "
            "{true_positives} | {false_positives} | {precision} | {base_rate} | {precision_lift} | "
            "{false_discovery_rate} |".format(**{key: markdown_value(value) for key, value in row.items()})
        )
    lines.extend(
        [
            "",
            "## Regime Target Match",
            "",
            "| Side | Candidate | State | Status | Signals | Precision | Base | Lift | FDR | Score |",
            "|---|---|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in regime_target_match.to_dicts():
        lines.append(
            "| {side} | {candidate_name} | {regime_state} | {target_match_status} | {signals} | "
            "{precision} | {base_rate} | {precision_lift} | {false_discovery_rate} | {target_match_score} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Change-Risk Target Match",
            "",
            "| Side | Candidate | Flag | Value | Status | Signals | Precision | Base | Lift | FDR |",
            "|---|---|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in change_risk_target_match.to_dicts():
        lines.append(
            "| {side} | {candidate_name} | {change_flag} | {change_flag_value} | {target_match_status} | "
            "{signals} | {precision} | {base_rate} | {precision_lift} | {false_discovery_rate} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Suppression Candidates",
            "",
            "| Side | Candidate | Context | Signals | Lift | FDR | Suppression Score |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in suppression_candidates.to_dicts()[:30]:
        lines.append(
            "| {side} | {candidate_name} | {suppression_context} | {signals} | "
            "{precision_lift} | {false_discovery_rate} | {suppression_score} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- A useful regime layer should show materially different precision/lift/FDR by state.",
            "- High regime entropy or frequent change alarms should be treated as risk context, not as a signal by itself.",
            "- Favorable/avoid labels are diagnostic; use them for the next shadow suppression replay before changing live routing.",
            "- This command does not modify router decisions; promotion requires a separate walk-forward router mode.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def summarize_stage(context: pl.DataFrame, changes: pl.DataFrame, state_metrics: pl.DataFrame) -> dict[str, Any]:
    return {
        "context_rows": context.height,
        "change_events": changes.height,
        "state_metric_rows": state_metrics.height,
        "sides": sorted(context["side"].unique().to_list()) if "side" in context.columns and not context.is_empty() else [],
        "candidates": sorted(context["candidate_name"].unique().to_list())
        if "candidate_name" in context.columns and not context.is_empty()
        else [],
    }


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def run_root_for_args() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_regime_diagnostic"


if __name__ == "__main__":
    raise SystemExit(main())
