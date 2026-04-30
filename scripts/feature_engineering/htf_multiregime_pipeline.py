from __future__ import annotations

"""Multi-regime HTF pipeline.

This module is the shared source of truth for HTF batch materialization across
`8h`, `24h`, and `7d`. It preserves legacy `8h` artifact names and compatibility
columns where that avoids breaking downstream consumers. In particular,
`period_8h_start` remains the canonical batch-start column name even when the
active regime is not `8h`.
"""

import gc
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import numpy as np
import pandas as pd
import polars as pl

if TYPE_CHECKING:
    from scripts.feature_engineering.compute_htf_features import HTFFeatureEngine

from scripts.feature_engineering.htf_helper_cache import (
    DEFAULT_HELPER_NAMES,
    build_helper_cache_exact,
    get_helper_contract_metadata,
    materialize_helpers_from_cache,
)
from scripts.feature_engineering.htf_artifact_utils import (
    artifact_meta_payload as _shared_artifact_meta_payload,
    artifact_rebuild_reasons as _shared_artifact_rebuild_reasons,
    clear_artifact_target as _shared_clear_artifact_target,
    find_batch_missing_required_columns as _shared_find_batch_missing_required_columns,
    fingerprint_batch_dir as _shared_fingerprint_batch_dir,
    fingerprint_paths as _shared_fingerprint_paths,
    load_json_safe as _shared_load_json_safe,
    prepare_stage_rebuild as _shared_prepare_stage_rebuild,
    schema_columns_for_batch_dir as _shared_schema_columns_for_batch_dir,
)
from scripts.feature_engineering.htf_feature_acceptance import (
    FINAL_OUTPUT_FEATURE_POLICY_VERSION,
    get_final_output_excluded_columns,
)
from scripts.feature_engineering.htf_kernels import (
    _compute_past_distance_metrics as _shared_compute_past_distance_metrics,
    compute_4class_labels as _shared_compute_4class_labels,
    compute_distance_metrics as _shared_compute_distance_metrics,
    compute_hybrid_distance_metrics as _shared_compute_hybrid_distance_metrics,
)

try:
    from numba import njit
except ImportError:  # pragma: no cover - shell fallback for lightweight verification
    def njit(*args, **kwargs):
        if args and callable(args[0]) and len(args) == 1 and not kwargs:
            return args[0]

        def decorator(func):
            return func

        return decorator


@dataclass(frozen=True)
class BatchRegimeConfig:
    name: str
    duration_hours: int
    shift_hours: int
    entry_window_hours: int
    anchor_utc: datetime


REGIME_CONFIGS: dict[str, BatchRegimeConfig] = {
    "8h": BatchRegimeConfig(
        name="8h",
        duration_hours=8,
        shift_hours=4,
        entry_window_hours=4,
        anchor_utc=datetime(1970, 1, 1, 0, 0, tzinfo=timezone.utc),
    ),
    "24h": BatchRegimeConfig(
        name="24h",
        duration_hours=24,
        shift_hours=12,
        entry_window_hours=12,
        anchor_utc=datetime(1970, 1, 1, 0, 0, tzinfo=timezone.utc),
    ),
    "7d": BatchRegimeConfig(
        name="7d",
        duration_hours=168,
        shift_hours=84,
        entry_window_hours=84,
        anchor_utc=datetime(1970, 1, 5, 0, 0, tzinfo=timezone.utc),
    ),
}

TF_MINUTES = {"1m": 1, "15m": 15}
DISTANCE_TIMEFRAMES = ("15m",)
UPSTREAM_TIMEFRAMES = ("1m", "15m")
TARGET_TIMEFRAMES = ("1m",)
SOURCE_AUGMENTED_FEATURE_TFS = ("1m", "15m")
HELPER_NAMES = DEFAULT_HELPER_NAMES
MIN_REMAINING_15M = 1
MIN_REMAINING_1M_FROM_15M = 15
BB_PERIOD = 20
BB_STD = 2.0
OUTLIER_PERCENTILE = 0.05

BASE_SCOPE_NAMES = {
    "backtest": "htf_backtest",
    "features": "htf_features",
    "labels": "htf_4class_labels",
    "optimized": "htf_optimized",
    "helpers": "htf_with_helpers",
}
LEGACY_8H_SHIFT_NAMES = {
    "backtest": "htf_backtest_shift4h",
    "features": "htf_features_shift4h",
    "labels": "htf_4class_labels_shift4h",
    "optimized": "htf_optimized_shift4h",
    "helpers": "htf_with_helpers_shift4h",
}

FAMILY_META_COLS = [
    # Legacy compatibility alias: reused for every regime even when the batch is
    # `24h` or `7d`. The actual regime is recorded in `batch_regime`.
    "period_8h_start",
    "batch_family",
    "family_batch_id",
    "family_period_start",
    "family_period_end",
    "family_bar_pos",
    "source_base_batch_id",
    "source_base_period_start",
    "source_half_in_base",
    "is_label_half",
    "bar_in_batch_norm",
    "batch_regime",
    "batch_duration_hours",
    "family_shift_hours",
    "anchor_utc",
    "entry_window_hours",
]
COMBINED_OUTPUT_COLS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "period_8h_start",
    "batch_id",
    *FAMILY_META_COLS[1:],
]


@dataclass
class MultiRegimeHTFConfig:
    project_root: Path
    data_dir: Path
    raw_data_dir: Path
    pipeline_artifact_version: str
    thresholds_by_tf: dict[str, dict[str, float]]
    distance_windows_by_tf: dict[str, dict[str, int]]
    build_regimes: tuple[str, ...] = ("8h", "24h", "7d")
    validate_regimes: tuple[str, ...] | None = None
    rebuild_existing: bool = False
    force_recreate_combined: bool = False
    min_raw_lead_hours_for_update: float = 0.0
    feature_incremental_update: bool = True
    feature_incremental_overlap_batches_by_tf: dict[str, int] = field(
        default_factory=lambda: {"1m": 2, "15m": 2}
    )
    feature_context_batches_by_tf: dict[str, int] = field(
        default_factory=lambda: {"1m": 2, "15m": 2}
    )
    incremental_distance_metrics: bool = True
    incremental_distance_tail_batches_by_tf: dict[str, int] = field(
        default_factory=lambda: {"15m": 8}
    )
    incremental_label_update: bool = True
    incremental_label_tail_batches_by_tf: dict[str, int] = field(
        default_factory=lambda: {"1m": 8}
    )
    incremental_helpers_skip_unchanged: bool = True
    helper_overlap_batches_by_tf: dict[str, int] = field(
        default_factory=lambda: {"1m": 2}
    )
    use_canonical_helper_cache: bool = True
    helper_cache_dir: Path | None = None
    incremental_helper_cache_update: bool = True
    helper_cache_overlap_batches_by_tf: dict[str, int] = field(
        default_factory=lambda: {"1m": 2, "15m": 2}
    )
    write_helpers_combined: bool = False
    run_optimization: bool = True
    run_helpers: bool = True
    run_validation: bool = True
    breakout_threshold: float = 2.1
    risk_ratio: float = 2.5
    breakfree_threshold_1m: float = 0.001
    date_start: datetime = datetime(2021, 1, 1)
    date_end: datetime | None = None
    smoke_mode: bool = False
    smoke_start: datetime | None = None
    smoke_end: datetime | None = None
    helper_warmup_by_tf: dict[str, int] = field(
        default_factory=lambda: {"1m": 20000, "15m": 5000}
    )
    helper_refit_every_by_tf: dict[str, int] = field(
        default_factory=lambda: {"1m": 10000, "15m": 2500}
    )
    usability_audit_enabled: bool = True
    usability_audit_null_rate_threshold: float = 0.25
    usability_audit_report_top_n: int = 20
    usability_audit_helper_prefix_batches: int = 20
    usability_audit_fail_on_all_null: bool = True
    usability_audit_fail_on_high_null: bool = False
    usability_audit_fail_on_constant: bool = True
    stage_progress_every_batches: int = 250
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None

    def effective_validate_regimes(self) -> tuple[str, ...]:
        return self.validate_regimes or self.build_regimes


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _stringify_progress_value(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return json.dumps(list(value))
    if isinstance(value, list):
        return json.dumps(value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _emit_progress(
    config: MultiRegimeHTFConfig,
    event: str,
    *,
    stage: str,
    **payload: Any,
) -> None:
    if config.progress_callback is None:
        return
    try:
        config.progress_callback(event, {"stage": stage, **payload})
    except Exception as exc:  # pragma: no cover - progress callbacks are best-effort
        print(f"[HTF][WARN] progress callback failed for {stage}: {exc}", flush=True)


def _result_summary(result: Any) -> str:
    if not isinstance(result, dict):
        return _stringify_progress_value(result)
    interesting = [
        "status",
        "run_mode",
        "rows",
        "batches",
        "written",
        "skipped",
        "valid_labels",
        "result_rows",
        "reason",
    ]
    parts = []
    for key in interesting:
        if key in result:
            parts.append(f"{key}={_stringify_progress_value(result[key])}")
    return ", ".join(parts)


def _log_stage_start(
    config: MultiRegimeHTFConfig,
    *,
    regime: str,
    family: str | None,
    tf: str | None,
    stage: str,
    detail: str = "",
) -> float:
    scope = [f"regime={regime}"]
    if family is not None:
        scope.append(f"family={family}")
    if tf is not None:
        scope.append(f"tf={tf}")
    scope.append(f"stage={stage}")
    if detail:
        scope.append(detail)
    message = " | ".join(scope)
    print(f"[HTF][START] {message}", flush=True)
    _emit_progress(
        config,
        "start",
        stage=f"{regime}/{family or '-'}{('/' + tf) if tf else ''}/{stage}",
        regime=regime,
        family=family,
        tf=tf,
        detail=detail,
    )
    return time.time()


def _log_stage_done(
    config: MultiRegimeHTFConfig,
    started_at: float,
    *,
    regime: str,
    family: str | None,
    tf: str | None,
    stage: str,
    result: Any,
) -> None:
    elapsed = time.time() - started_at
    summary = _result_summary(result)
    scope = [f"regime={regime}"]
    if family is not None:
        scope.append(f"family={family}")
    if tf is not None:
        scope.append(f"tf={tf}")
    scope.append(f"stage={stage}")
    scope.append(f"elapsed={_format_elapsed(elapsed)}")
    if summary:
        scope.append(summary)
    print(f"[HTF][DONE ] {' | '.join(scope)}", flush=True)
    _emit_progress(
        config,
        "done",
        stage=f"{regime}/{family or '-'}{('/' + tf) if tf else ''}/{stage}",
        regime=regime,
        family=family,
        tf=tf,
        elapsed_seconds=round(elapsed, 3),
        summary=summary,
    )


def _log_batch_progress(
    config: MultiRegimeHTFConfig,
    label: str,
    current: int,
    total: int,
    *,
    started_at: float,
) -> None:
    if total <= 0:
        return
    every = max(1, int(config.stage_progress_every_batches))
    if current != 1 and current != total and current % every != 0:
        return
    progress = current / total
    elapsed = time.time() - started_at
    eta = (elapsed / progress) * (1.0 - progress) if progress > 0 else 0.0
    print(
        f"  {label}: {current:,}/{total:,} ({progress * 100:5.1f}%) | "
        f"elapsed={_format_elapsed(elapsed)} | eta~{_format_elapsed(eta)}",
        flush=True,
    )


def compute_distance_metrics(
    close,
    high,
    low,
    batch_id,
    bar_pos,
    bars_per_batch,
    min_remaining,
):
    return _shared_compute_distance_metrics(
        close,
        high,
        low,
        batch_id,
        bar_pos,
        bars_per_batch,
        min_remaining,
    )


def compute_hybrid_distance_metrics(
    close_entry,
    batch_id_entry,
    bar_pos_15m_for_entry,
    high_15m,
    low_15m,
    batch_id_15m,
    bar_pos_15m,
    min_remaining,
    outlier_pct,
):
    return _shared_compute_hybrid_distance_metrics(
        close_entry,
        batch_id_entry,
        bar_pos_15m_for_entry,
        high_15m,
        low_15m,
        batch_id_15m,
        bar_pos_15m,
        min_remaining,
        outlier_pct,
    )


def _compute_past_distance_metrics(close, high, low, bar_pos, window, outlier_pct):
    return _shared_compute_past_distance_metrics(
        close,
        high,
        low,
        bar_pos,
        window,
        outlier_pct,
    )


def compute_4class_labels(
    df: pl.DataFrame,
    breakout_thresh: float,
    risk_thresh: float,
) -> pl.DataFrame:
    return _shared_compute_4class_labels(df, breakout_thresh, risk_thresh)


def _fingerprint_paths(paths: list[Path]) -> dict[str, Any]:
    return _shared_fingerprint_paths(paths, include_paths=True)


def _load_json_safe(path: Path) -> dict[str, Any] | None:
    return _shared_load_json_safe(path)


def _fingerprint_batch_dir(directory: Path) -> dict[str, Any]:
    return _shared_fingerprint_batch_dir(directory, include_paths=True)


def _schema_columns_for_batch_dir(directory: Path) -> list[str]:
    return _shared_schema_columns_for_batch_dir(directory)


def _find_batch_missing_required_columns(
    directory: Path,
    required_cols: set[str],
) -> dict[str, Any] | None:
    return _shared_find_batch_missing_required_columns(directory, required_cols)


def _clear_artifact_target(path: Path) -> list[str]:
    return _shared_clear_artifact_target(path)


def _stage_version(
    config: MultiRegimeHTFConfig,
    stage: str,
    family: str,
) -> str:
    suffix = f"{stage}-{family.lower()}-v1"
    return f"{config.pipeline_artifact_version}-{suffix}"


def _artifact_rebuild_reasons(
    *,
    meta_path: Path,
    artifact_version: str,
    family: str,
    timeframe: str,
    source_fingerprint: dict[str, Any],
    schema_columns: list[str] | None = None,
) -> list[str]:
    return _shared_artifact_rebuild_reasons(
        meta_path=meta_path,
        artifact_version=artifact_version,
        family=family,
        timeframe=timeframe,
        source_fingerprint=source_fingerprint,
        schema_columns=schema_columns,
    )


def _artifact_meta_payload(
    *,
    artifact_version: str,
    family: str,
    timeframe: str,
    source_fingerprint: dict[str, Any],
    schema_columns: list[str],
    rebuild_mode: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _shared_artifact_meta_payload(
        artifact_version=artifact_version,
        family=family,
        timeframe=timeframe,
        source_fingerprint=source_fingerprint,
        schema_columns=schema_columns,
        rebuild_mode=rebuild_mode,
        extra=extra,
        updated_at_mode="offset",
    )


def _prepare_stage_rebuild(
    *,
    stage_name: str,
    meta_path: Path,
    artifact_version: str,
    family: str,
    timeframe: str,
    source_fingerprint: dict[str, Any],
    schema_columns: list[str],
    output_targets: list[Path],
    inspect_batch_dir: Path | None = None,
    required_batch_columns: set[str] | None = None,
    full_rebuild_reasons: set[str] | None = None,
) -> tuple[list[str], str]:
    return _shared_prepare_stage_rebuild(
        stage_name=stage_name,
        meta_path=meta_path,
        artifact_version=artifact_version,
        family=family,
        timeframe=timeframe,
        source_fingerprint=source_fingerprint,
        schema_columns=schema_columns,
        output_targets=output_targets,
        inspect_batch_dir=inspect_batch_dir,
        required_batch_columns=required_batch_columns,
        full_rebuild_reasons=full_rebuild_reasons,
    )


def _batch_file_map(directory: Path) -> dict[int, Path]:
    return {
        int(path.stem.split("_")[1]): path
        for path in sorted(directory.glob("batch_*.parquet"))
        if path.stem.startswith("batch_")
    }


def _output_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    stats = (
        pl.scan_parquet(path)
        .select(
            [
                pl.len().alias("total_rows"),
                pl.col("timestamp").min().alias("min_ts"),
                pl.col("timestamp").max().alias("max_ts"),
                pl.col("batch_id").max().alias("max_batch"),
            ]
        )
        .collect()
    )
    return {
        "exists": True,
        "path": str(path),
        "total_rows": int(stats["total_rows"].item()),
        "min_ts": stats["min_ts"].item(),
        "max_ts": stats["max_ts"].item(),
        "max_batch": int(stats["max_batch"].item()) if stats["max_batch"].item() is not None else None,
    }


def _raw_dir_for_tf(config: MultiRegimeHTFConfig, tf: str) -> Path:
    raw_dir_name = "sorted-1m-bybit-linear" if tf == "1m" else "sorted-15m-bybit-linear"
    return config.raw_data_dir / raw_dir_name


def _select_incremental_label_batches(
    label_batches: set[int],
    existing_label_files: list[Path],
    tail_batches: int,
) -> tuple[set[int], set[int], list[int]]:
    sorted_label_batches = sorted(label_batches)
    if not sorted_label_batches:
        return set(), set(), []

    existing_ids = {
        int(path.stem.split("_")[1])
        for path in existing_label_files
        if path.stem.startswith("batch_")
    }
    missing_batches = sorted(set(sorted_label_batches) - existing_ids)
    tail_targets = sorted_label_batches[-tail_batches:]
    target_batches = set(tail_targets) | set(missing_batches)

    min_target = min(target_batches)
    max_target = max(target_batches)
    warmup_batch = min_target - 1
    compute_batches = {
        bid for bid in label_batches if (warmup_batch <= bid <= max_target)
    }
    return target_batches, compute_batches, missing_batches


def _bars_per_batch(regime: str, tf: str) -> int:
    cfg = REGIME_CONFIGS[regime]
    return int((cfg.duration_hours * 60) // TF_MINUTES[tf])


def _bars_per_half(regime: str, tf: str) -> int:
    return _bars_per_batch(regime, tf) // 2


def _entry_bar_limit(regime: str, tf: str) -> int:
    cfg = REGIME_CONFIGS[regime]
    return int(_bars_per_batch(regime, tf) * (cfg.entry_window_hours / cfg.duration_hours))


def _expected_valid_1m_rows(regime: str) -> int:
    return min(
        _bars_per_batch(regime, "1m") - MIN_REMAINING_1M_FROM_15M,
        _entry_bar_limit(regime, "1m"),
    )


def _eligible_label_batches_from_counts(
    counts_1m: pl.DataFrame,
    counts_15m: pl.DataFrame,
    regime: str,
) -> list[int]:
    if len(counts_1m) == 0 or len(counts_15m) == 0:
        return []

    last_1m = int(counts_1m["batch_id"].max())
    last_15m = int(counts_15m["batch_id"].max())
    valid_1m = counts_1m.filter(
        (pl.col("n") == _bars_per_batch(regime, "1m"))
        | ((pl.col("batch_id") == last_1m) & (pl.col("n") >= 1))
    )["batch_id"].to_list()
    valid_15m = counts_15m.filter(
        (pl.col("n") == _bars_per_batch(regime, "15m"))
        | ((pl.col("batch_id") == last_15m) & (pl.col("n") >= 1))
    )["batch_id"].to_list()
    return sorted(set(valid_1m) & set(valid_15m))


def _anchor_utc_str(regime: str) -> str:
    return REGIME_CONFIGS[regime].anchor_utc.isoformat()


def _family_anchor(regime: str, family: str) -> datetime:
    anchor = REGIME_CONFIGS[regime].anchor_utc
    if family == "C":
        anchor = anchor + timedelta(hours=REGIME_CONFIGS[regime].shift_hours)
    return anchor


def _family_scope(data_dir: Path, regime: str, family: str) -> dict[str, Path | str | int]:
    """Return artifact roots for a regime/family pair.

    `8h` keeps the original directory names for backward compatibility.
    Longer regimes get dedicated trees such as `*_24h` / `*_24h_shift12h`.
    """
    if regime == "8h":
        if family == "B":
            stage_dirs = {k: data_dir / v for k, v in BASE_SCOPE_NAMES.items()}
        else:
            stage_dirs = {k: data_dir / v for k, v in LEGACY_8H_SHIFT_NAMES.items()}
    else:
        shift_suffix = "" if family == "B" else f"_shift{REGIME_CONFIGS[regime].shift_hours}h"
        stage_dirs = {
            stage: data_dir / f"{base}_{regime}{shift_suffix}"
            for stage, base in BASE_SCOPE_NAMES.items()
        }

    for path in stage_dirs.values():
        Path(path).mkdir(parents=True, exist_ok=True)

    return {
        "family": family,
        "regime": regime,
        "shift_hours": 0 if family == "B" else REGIME_CONFIGS[regime].shift_hours,
        **stage_dirs,
    }


def _helper_cache_root(config: MultiRegimeHTFConfig) -> Path:
    root = config.helper_cache_dir or (config.data_dir / "htf_helper_cache")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _helper_cache_source(
    config: MultiRegimeHTFConfig,
    regime: str,
    family: str,
) -> tuple[Path, str]:
    if family == "B":
        return Path(_family_scope(config.data_dir, "8h", "B")["features"]) / "1m", "base_0h"
    shift_hours = REGIME_CONFIGS[regime].shift_hours
    return Path(_family_scope(config.data_dir, regime, "C")["features"]) / "1m", f"shift{shift_hours}h"


def _clear_batch_dir(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for batch_file in directory.glob("batch_*.parquet"):
        batch_file.unlink()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2, default=str)


def _stage_meta(
    stage: str,
    regime: str,
    family: str,
    tf: str,
    source_paths: list[Path],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = REGIME_CONFIGS[regime]
    return {
        "stage": stage,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "batch_regime": regime,
        "family": family,
        "timeframe": tf,
        "batch_duration_hours": int(cfg.duration_hours),
        "family_shift_hours": int(0 if family == "B" else cfg.shift_hours),
        "anchor_utc": _anchor_utc_str(regime),
        "entry_window_hours": int(cfg.entry_window_hours),
        "source_fingerprint": _fingerprint_paths(source_paths),
        **(extra or {}),
    }


def _period_start_expr(ts_col: str, regime: str, family: str) -> pl.Expr:
    anchor = _family_anchor(regime, family)
    anchor_us = int(anchor.timestamp() * 1_000_000)
    duration_us = int(REGIME_CONFIGS[regime].duration_hours * 3_600_000_000)
    ts_us = pl.col(ts_col).dt.replace_time_zone(None).dt.timestamp("us")
    return (
        (((ts_us - anchor_us) // duration_us) * duration_us) + anchor_us
    ).cast(pl.Datetime("us"))


def _add_family_metadata(
    df: pl.DataFrame,
    regime: str,
    tf: str,
    family: str,
    family_period_col: str,
    family_batch_col: str,
) -> pl.DataFrame:
    cfg = REGIME_CONFIGS[regime]
    bars_per_batch = _bars_per_batch(regime, tf)
    half_bars = _bars_per_half(regime, tf)

    df = df.with_columns(
        [
            pl.lit(family).alias("batch_family"),
            pl.col(family_batch_col).cast(pl.Int32).alias("family_batch_id"),
            pl.col(family_period_col)
            .dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC"))
            .alias("family_period_start"),
            (pl.col(family_period_col) + timedelta(hours=cfg.duration_hours))
            .dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC"))
            .alias("family_period_end"),
            (pl.col("timestamp").rank("ordinal").over(family_batch_col) - 1)
            .cast(pl.Int32)
            .alias("family_bar_pos"),
        ]
    )

    if "period_8h_start" not in df.columns:
        df = df.with_columns(
            pl.col(family_period_col)
            .dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC"))
            .alias("period_8h_start")
        )
    if "batch_id" not in df.columns:
        df = df.with_columns(pl.col(family_batch_col).cast(pl.Int32).alias("batch_id"))

    if "source_base_period_start" not in df.columns:
        df = df.with_columns(
            pl.col("period_8h_start")
            .cast(pl.Datetime("us", "UTC"))
            .alias("source_base_period_start")
        )
    if "source_base_batch_id" not in df.columns:
        df = df.with_columns(pl.col("batch_id").cast(pl.Int32).alias("source_base_batch_id"))

    df = df.with_columns(
        [
            pl.when(
                pl.col("timestamp").dt.replace_time_zone(None)
                < (
                    pl.col("source_base_period_start").dt.replace_time_zone(None)
                    + timedelta(hours=cfg.entry_window_hours)
                )
            )
            .then(pl.lit("L"))
            .otherwise(pl.lit("F"))
            .alias("source_half_in_base"),
            (pl.col("family_bar_pos") < half_bars).alias("is_label_half"),
            (
                pl.col("family_bar_pos").cast(pl.Float64)
                / max(1, bars_per_batch - 1)
            ).alias("bar_in_batch_norm"),
            pl.lit(regime).alias("batch_regime"),
            pl.lit(int(cfg.duration_hours)).alias("batch_duration_hours"),
            pl.lit(int(0 if family == "B" else cfg.shift_hours)).alias("family_shift_hours"),
            pl.lit(_anchor_utc_str(regime)).alias("anchor_utc"),
            pl.lit(int(cfg.entry_window_hours)).alias("entry_window_hours"),
        ]
    )
    return df


def _normalize_dt_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "tzinfo") and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def _apply_raw_time_filters(
    lf: pl.LazyFrame,
    config: MultiRegimeHTFConfig,
) -> pl.LazyFrame:
    lf = lf.with_columns(pl.col("timestamp").dt.replace_time_zone(None).alias("ts_norm"))
    if config.date_start is not None:
        lf = lf.filter(pl.col("ts_norm") >= config.date_start)
    if config.date_end is not None:
        lf = lf.filter(pl.col("ts_norm") < config.date_end)
    if config.smoke_mode:
        if config.smoke_start is not None:
            lf = lf.filter(pl.col("ts_norm") >= config.smoke_start)
        if config.smoke_end is not None:
            lf = lf.filter(pl.col("ts_norm") < config.smoke_end)
    return lf


def _combined_required_columns() -> set[str]:
    return set(COMBINED_OUTPUT_COLS)


def _build_base_combined(config: MultiRegimeHTFConfig, regime: str, tf: str) -> dict[str, Any]:
    raw_dir = _raw_dir_for_tf(config, tf)
    scope = _family_scope(config.data_dir, regime, "B")
    output_path = Path(scope["backtest"]) / f"{tf}_HTF_combined.parquet"
    meta_path = Path(scope["backtest"]) / f"{tf}_HTF_combined_meta.json"

    artifact_version = _stage_version(config, "combined", "B")
    required_columns = _combined_required_columns()
    output_info = _output_stats(output_path)

    if not raw_dir.exists() or not list(raw_dir.glob("*.parquet")):
        if output_info["exists"]:
            return {
                **output_info,
                "meta_path": str(meta_path),
                "status": "current_no_raw",
                "run_mode": "current",
                "update_reason": "raw_missing",
                "rows": output_info.get("total_rows", 0),
                "batches": output_info.get("max_batch", 0) or 0,
            }
        raise ValueError(f"Raw dir not found or empty for {regime}/{tf}: {raw_dir}")

    raw_files = sorted(raw_dir.glob("*.parquet"))
    raw_scan = _apply_raw_time_filters(pl.scan_parquet(raw_dir / "*.parquet"), config)
    raw_stats = raw_scan.select(
        [
            pl.len().alias("total_rows"),
            pl.col("timestamp").min().alias("min_ts"),
            pl.col("timestamp").max().alias("max_ts"),
        ]
    ).collect()
    raw_total_rows = int(raw_stats["total_rows"].item())
    raw_max_ts = raw_stats["max_ts"].item()

    existing_schema_ok = False
    if output_info["exists"]:
        output_cols = set(pl.scan_parquet(output_path).collect_schema().names())
        existing_schema_ok = required_columns.issubset(output_cols)

    needs_update = False
    update_reason = ""
    run_mode = "current"
    status = "current"
    if config.rebuild_existing or config.force_recreate_combined:
        needs_update = True
        update_reason = "forced"
        run_mode = "full_recompute"
    elif not output_info["exists"]:
        needs_update = True
        update_reason = "missing"
        run_mode = "full_first_build"
    elif not existing_schema_ok:
        needs_update = True
        update_reason = "schema_columns"
        run_mode = "full_recompute"
    else:
        combined_max_ts = output_info.get("max_ts")
        raw_max_cmp = _normalize_dt_value(raw_max_ts)
        combined_max_cmp = _normalize_dt_value(combined_max_ts)
        if raw_max_cmp is not None and combined_max_cmp is not None and raw_max_cmp > combined_max_cmp:
            time_diff = raw_max_cmp - combined_max_cmp
            hours_diff = (
                time_diff.total_seconds() / 3600
                if hasattr(time_diff, "total_seconds")
                else time_diff / timedelta(hours=1)
            )
            if hours_diff >= float(config.min_raw_lead_hours_for_update):
                needs_update = True
                update_reason = f"new_data (+{hours_diff:.1f}h)"
                run_mode = "full_recompute"

    if not needs_update:
        return {
            **output_info,
            "meta_path": str(meta_path),
            "status": status,
            "run_mode": run_mode,
            "update_reason": "up_to_date",
            "rows": output_info.get("total_rows", 0),
            "batches": output_info.get("max_batch", 0) or 0,
        }

    df = _apply_raw_time_filters(pl.scan_parquet(raw_dir / "*.parquet"), config).collect()
    if df.is_empty():
        raise ValueError(f"No raw rows available for {regime}/{tf} after filters")

    rows_before_dedup = len(df)
    df = df.sort("ts_norm").unique(subset=["ts_norm"], keep="last", maintain_order=True)
    rows_after_dedup = len(df)
    duplicate_rows_removed = rows_before_dedup - rows_after_dedup

    df = df.with_columns(_period_start_expr("ts_norm", regime, "B").alias("period_8h_start"))
    batch_mapping = (
        df.select("period_8h_start")
        .unique()
        .sort("period_8h_start")
        .with_row_index("batch_id")
        .with_columns((pl.col("batch_id") + 1).cast(pl.Int32))
    )
    df = df.join(batch_mapping, on="period_8h_start", how="left")
    df = _add_family_metadata(
        df=df,
        regime=regime,
        tf=tf,
        family="B",
        family_period_col="period_8h_start",
        family_batch_col="batch_id",
    )
    df_final = (
        df.select(
            [
                "timestamp",
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("volume").cast(pl.Float64),
                pl.col("period_8h_start")
                .dt.replace_time_zone("UTC")
                .cast(pl.Datetime("us", "UTC")),
                "batch_id",
                *COMBINED_OUTPUT_COLS[8:],
            ]
        )
        .sort(["batch_id", "timestamp"])
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_final.write_parquet(output_path)
    source_fingerprint = _fingerprint_paths(raw_files)
    _write_json(
        meta_path,
        _artifact_meta_payload(
            artifact_version=artifact_version,
            family="B",
            timeframe=tf,
            source_fingerprint=source_fingerprint,
            schema_columns=COMBINED_OUTPUT_COLS,
            rebuild_mode=run_mode,
            extra={
                "stage": "combined",
                "batch_regime": regime,
                "batch_duration_hours": int(REGIME_CONFIGS[regime].duration_hours),
                "family_shift_hours": 0,
                "anchor_utc": _anchor_utc_str(regime),
                "entry_window_hours": int(REGIME_CONFIGS[regime].entry_window_hours),
                "status": "created",
                "update_reason": update_reason,
                "rows": int(len(df_final)),
                "batches": int(df_final["batch_id"].n_unique()),
                "rows_per_batch": int(_bars_per_batch(regime, tf)),
                "output_path": str(output_path),
                "raw_total_rows": raw_total_rows,
                "raw_max_ts": raw_max_ts,
                "rows_before_dedup": int(rows_before_dedup),
                "rows_after_dedup": int(rows_after_dedup),
                "duplicate_rows_removed": int(duplicate_rows_removed),
                "min_ts": df_final["timestamp"].min(),
                "max_ts": df_final["timestamp"].max(),
            },
        ),
    )
    return {
        "path": output_path,
        "meta_path": meta_path,
        "rows": int(len(df_final)),
        "batches": int(df_final["batch_id"].n_unique()),
        "status": "created",
        "run_mode": run_mode,
        "update_reason": update_reason,
    }


def _build_shifted_combined(
    config: MultiRegimeHTFConfig,
    regime: str,
    tf: str,
) -> dict[str, Any]:
    base_scope = _family_scope(config.data_dir, regime, "B")
    shift_scope = _family_scope(config.data_dir, regime, "C")
    base_path = Path(base_scope["backtest"]) / f"{tf}_HTF_combined.parquet"
    base_meta_path = Path(base_scope["backtest"]) / f"{tf}_HTF_combined_meta.json"
    output_path = Path(shift_scope["backtest"]) / f"{tf}_HTF_combined.parquet"
    meta_path = Path(shift_scope["backtest"]) / f"{tf}_HTF_combined_meta.json"

    artifact_version = _stage_version(config, "combined", "C")
    source_fingerprint = {
        "base_combined": _fingerprint_paths([base_path, base_meta_path]),
    }
    existing_cols = set(pl.scan_parquet(output_path).collect_schema().names()) if output_path.exists() else set()
    reasons, rebuild_mode = _prepare_stage_rebuild(
        stage_name=f"{regime} shift combined {tf}",
        meta_path=meta_path,
        artifact_version=artifact_version,
        family="C",
        timeframe=tf,
        source_fingerprint=source_fingerprint,
        schema_columns=COMBINED_OUTPUT_COLS,
        output_targets=[output_path, meta_path],
    )
    if output_path.exists() and existing_cols and not _combined_required_columns().issubset(existing_cols):
        reasons.append("schema_columns")
        rebuild_mode = "full"
        _clear_artifact_target(output_path)
        _clear_artifact_target(meta_path)

    if config.rebuild_existing:
        reasons = ["forced_rebuild"]
        rebuild_mode = "full"
        _clear_artifact_target(output_path)
        _clear_artifact_target(meta_path)

    if not reasons and output_path.exists():
        stats = _output_stats(output_path)
        return {
            **stats,
            "meta_path": str(meta_path),
            "status": "current",
            "run_mode": "current",
            "update_reason": "up_to_date",
            "rows": stats.get("total_rows", 0),
            "batches": stats.get("max_batch", 0) or 0,
        }

    base_df = pl.read_parquet(base_path).sort("timestamp")
    inherited_cols = [
        col
        for col in [
            "batch_family",
            "family_batch_id",
            "family_period_start",
            "family_period_end",
            "family_bar_pos",
            "source_base_batch_id",
            "source_base_period_start",
            "source_half_in_base",
            "is_label_half",
            "bar_in_batch_norm",
            "batch_regime",
            "batch_duration_hours",
            "family_shift_hours",
            "anchor_utc",
            "entry_window_hours",
        ]
        if col in base_df.columns
    ]
    min_base_start = base_df["period_8h_start"].min()
    min_base_naive = min_base_start.replace(tzinfo=None)

    df = base_df.drop(inherited_cols).with_columns(
        _period_start_expr("timestamp", regime, "C").alias("family_period_start_raw")
    )
    df = df.filter(
        pl.col("family_period_start_raw")
        >= pl.lit(min_base_naive + timedelta(hours=REGIME_CONFIGS[regime].shift_hours))
    )
    batch_mapping = (
        df.select("family_period_start_raw")
        .unique()
        .sort("family_period_start_raw")
        .with_row_index("shift_family_batch_id")
        .with_columns((pl.col("shift_family_batch_id") + 1).cast(pl.Int32))
    )
    df = df.join(batch_mapping, on="family_period_start_raw", how="left")
    df = _add_family_metadata(
        df=df,
        regime=regime,
        tf=tf,
        family="C",
        family_period_col="family_period_start_raw",
        family_batch_col="shift_family_batch_id",
    ).with_columns(
        [
            pl.col("family_period_start").alias("period_8h_start"),
            pl.col("family_batch_id").alias("batch_id"),
        ]
    )
    df_final = df.select(COMBINED_OUTPUT_COLS).sort(["batch_id", "timestamp"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_final.write_parquet(output_path)
    _write_json(
        meta_path,
        _artifact_meta_payload(
            artifact_version=artifact_version,
            family="C",
            timeframe=tf,
            source_fingerprint=source_fingerprint,
            schema_columns=COMBINED_OUTPUT_COLS,
            rebuild_mode=rebuild_mode,
            extra={
                "stage": "combined",
                "batch_regime": regime,
                "batch_duration_hours": int(REGIME_CONFIGS[regime].duration_hours),
                "family_shift_hours": int(REGIME_CONFIGS[regime].shift_hours),
                "anchor_utc": _anchor_utc_str(regime),
                "entry_window_hours": int(REGIME_CONFIGS[regime].entry_window_hours),
                "status": "created",
                "update_reason": "source_refresh" if reasons else "forced",
                "rebuild_reasons": reasons,
                "rows": int(len(df_final)),
                "batches": int(df_final["batch_id"].n_unique()),
                "rows_per_batch": int(_bars_per_batch(regime, tf)),
                "output_path": str(output_path),
                "min_ts": df_final["timestamp"].min(),
                "max_ts": df_final["timestamp"].max(),
            },
        ),
    )
    return {
        "path": output_path,
        "meta_path": meta_path,
        "rows": int(len(df_final)),
        "batches": int(df_final["batch_id"].n_unique()),
        "status": "created",
        "run_mode": rebuild_mode,
        "update_reason": "source_refresh" if reasons else "forced",
    }


def _init_feature_engine(config: MultiRegimeHTFConfig):
    from scripts.feature_engineering.compute_htf_features import HTFFeatureEngine

    if str(config.project_root) not in sys.path:
        sys.path.insert(0, str(config.project_root))
    engine = HTFFeatureEngine(data_dir=config.raw_data_dir, verbose=False)
    engine.discover_available_sources()
    return engine


def _feature_source_fingerprint(
    config: MultiRegimeHTFConfig,
    engine: HTFFeatureEngine,
    combined_path: Path,
    tf: str,
) -> dict[str, Any]:
    auxiliary_paths = (
        engine.get_source_paths_for_timeframe(tf)
        if tf in SOURCE_AUGMENTED_FEATURE_TFS
        else []
    )
    return {
        "combined": _fingerprint_paths([combined_path]),
        "auxiliary_sources": _fingerprint_paths(auxiliary_paths),
    }


def _expected_feature_schema_columns(
    engine: HTFFeatureEngine,
    tf: str,
    distance_windows: dict[str, int],
) -> list[str]:
    feature_cols = engine.estimate_feature_output_columns(
        tf,
        include_auxiliary_sources=tf in SOURCE_AUGMENTED_FEATURE_TFS,
        distance_windows=distance_windows,
    )
    return [
        *feature_cols,
        "batch_id",
        *FAMILY_META_COLS,
    ]


def _feature_value_cols(df: pl.DataFrame) -> list[str]:
    meta = {"timestamp", "batch_id", *FAMILY_META_COLS}
    return [col for col in df.columns if col not in meta]


def _build_shifted_feature_batches_from_base(
    config: MultiRegimeHTFConfig,
    regime: str,
    tf: str,
) -> dict[str, Any]:
    source_scope = _family_scope(config.data_dir, regime, "B")
    output_scope = _family_scope(config.data_dir, regime, "C")
    source_dir = Path(source_scope["features"]) / tf
    output_dir = Path(output_scope["features"]) / tf
    combined_path = Path(output_scope["backtest"]) / f"{tf}_HTF_combined.parquet"
    combined_meta_path = Path(output_scope["backtest"]) / f"{tf}_HTF_combined_meta.json"
    meta_path = output_dir / "_build_meta.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    if not source_dir.exists() or not combined_path.exists():
        return {"written": 0, "skipped": 0, "status": "missing_inputs"}

    sample_feature_files = sorted(source_dir.glob("batch_*.parquet"))
    if not sample_feature_files:
        return {"written": 0, "skipped": 0, "status": "missing_source_features"}

    schema_columns = pl.scan_parquet(str(sample_feature_files[0])).collect_schema().names()
    artifact_version = _stage_version(config, "features", "C")
    source_fingerprint = {
        "base_features": _fingerprint_batch_dir(source_dir),
        "shift_combined": _fingerprint_paths([combined_path, combined_meta_path]),
    }
    rebuild_reasons, rebuild_mode = _prepare_stage_rebuild(
        stage_name=f"{regime} shift features {tf}",
        meta_path=meta_path,
        artifact_version=artifact_version,
        family="C",
        timeframe=tf,
        source_fingerprint=source_fingerprint,
        schema_columns=schema_columns,
        output_targets=[output_dir, meta_path],
        inspect_batch_dir=output_dir,
        required_batch_columns=set(["timestamp", "batch_id", *FAMILY_META_COLS]),
        full_rebuild_reasons={
            "missing_meta",
            "artifact_version",
            "family",
            "timeframe",
            "schema_columns",
            "legacy_schema",
        },
    )
    if config.rebuild_existing:
        rebuild_reasons = ["forced_rebuild"]
        rebuild_mode = "full_recompute"
        _clear_artifact_target(output_dir)
        _clear_artifact_target(meta_path)

    meta_all = pl.read_parquet(combined_path, columns=["timestamp", "batch_id", *FAMILY_META_COLS])
    written = 0
    skipped = 0
    batch_ids = sorted(meta_all["batch_id"].unique().to_list())
    progress_started_at = time.time()
    for idx, batch_id in enumerate(batch_ids, 1):
        meta_batch = meta_all.filter(pl.col("batch_id") == batch_id).sort("timestamp")
        out_path = output_dir / f"batch_{int(batch_id):04d}.parquet"
        source_batch_ids = sorted(
            meta_batch["source_base_batch_id"].drop_nulls().unique().to_list()
        )
        source_paths = [
            source_dir / f"batch_{int(source_batch_id):04d}.parquet"
            for source_batch_id in source_batch_ids
        ]
        existing_source_paths = [path for path in source_paths if path.exists()]
        sources_available = bool(source_paths) and len(existing_source_paths) == len(source_paths)
        source_inputs_newer = False
        if out_path.exists() and sources_available:
            out_mtime = int(out_path.stat().st_mtime_ns)
            source_inputs_newer = any(
                int(path.stat().st_mtime_ns) > out_mtime
                for path in existing_source_paths
            )
        if out_path.exists():
            existing = pl.read_parquet(out_path)
            required_raw_cols = {"open", "high", "low", "close", "volume"}
            has_required_raw_cols = required_raw_cols.issubset(existing.columns)
            same_rows = len(existing) == len(meta_batch)
            same_ts = same_rows and existing["timestamp"].to_list() == meta_batch["timestamp"].to_list()
            if (
                has_required_raw_cols
                and same_ts
                and sources_available
                and not source_inputs_newer
                and not config.rebuild_existing
            ):
                skipped += 1
                _log_batch_progress(
                    config,
                    f"{regime}/C/{tf} shifted feature batches",
                    idx,
                    len(batch_ids),
                    started_at=progress_started_at,
                )
                continue

        src_parts: list[pl.DataFrame] = []
        for src_path in source_paths:
            if src_path.exists():
                src_parts.append(pl.read_parquet(src_path))
        if not src_parts:
            continue

        src_df = pl.concat(src_parts, how="diagonal_relaxed")
        value_cols = _feature_value_cols(src_df)
        df_out = (
            src_df.select(["timestamp"] + value_cols)
            .join(meta_batch, on="timestamp", how="inner")
            .sort(["batch_id", "timestamp"])
        )
        df_out.write_parquet(out_path)
        written += 1
        _log_batch_progress(
            config,
            f"{regime}/C/{tf} shifted feature batches",
            idx,
            len(batch_ids),
            started_at=progress_started_at,
        )

    _write_json(
        meta_path,
        _artifact_meta_payload(
            artifact_version=artifact_version,
            family="C",
            timeframe=tf,
            source_fingerprint=source_fingerprint,
            schema_columns=schema_columns,
            rebuild_mode=rebuild_mode,
            extra={
                "stage": "features",
                "batch_regime": regime,
                "batch_duration_hours": int(REGIME_CONFIGS[regime].duration_hours),
                "family_shift_hours": int(REGIME_CONFIGS[regime].shift_hours),
                "anchor_utc": _anchor_utc_str(regime),
                "entry_window_hours": int(REGIME_CONFIGS[regime].entry_window_hours),
                "rebuild_reasons": rebuild_reasons,
                "output_dir": str(output_dir),
                "written": int(written),
                "skipped": int(skipped),
                "batch_count": int(len(list(output_dir.glob("batch_*.parquet")))),
            },
        ),
    )
    return {
        "rows": int(meta_all.height),
        "batches": int(meta_all["batch_id"].n_unique()),
        "output_dir": output_dir,
        "written": int(written),
        "skipped": int(skipped),
        "status": "created" if written > 0 else "current",
        "run_mode": rebuild_mode if written > 0 else "current",
    }


def _build_feature_batches(
    config: MultiRegimeHTFConfig,
    engine: HTFFeatureEngine,
    regime: str,
    family: str,
    tf: str,
) -> dict[str, Any]:
    if family == "C":
        return _build_shifted_feature_batches_from_base(config=config, regime=regime, tf=tf)

    scope = _family_scope(config.data_dir, regime, family)
    combined_path = Path(scope["backtest"]) / f"{tf}_HTF_combined.parquet"
    output_dir = Path(scope["features"]) / tf
    meta_path = output_dir / "_build_meta.json"
    output_dir.mkdir(parents=True, exist_ok=True)

    df_full = pl.read_parquet(combined_path).sort("timestamp")
    if df_full.is_empty():
        raise ValueError(f"No combined rows available for features: {regime}/{family}/{tf}")

    combined_batch_ids = sorted(df_full["batch_id"].unique().drop_nulls().to_list())
    combined_batch_set = set(combined_batch_ids)
    combined_max_batch = combined_batch_ids[-1]
    expected_schema_columns = _expected_feature_schema_columns(
        engine,
        tf,
        config.distance_windows_by_tf.get(tf, {}),
    )
    feature_source_fingerprint = _feature_source_fingerprint(
        config,
        engine,
        combined_path,
        tf,
    )
    feature_rebuild_reasons, feature_rebuild_mode = _prepare_stage_rebuild(
        stage_name=f"{regime} features {family}/{tf}",
        meta_path=meta_path,
        artifact_version=_stage_version(config, "features", family),
        family=family,
        timeframe=tf,
        source_fingerprint=feature_source_fingerprint,
        schema_columns=expected_schema_columns,
        output_targets=[output_dir, meta_path],
        inspect_batch_dir=output_dir,
        required_batch_columns=set(expected_schema_columns),
        full_rebuild_reasons={
            "missing_meta",
            "artifact_version",
            "family",
            "timeframe",
            "schema_columns",
            "legacy_schema",
        },
    )
    if config.rebuild_existing:
        feature_rebuild_reasons = ["forced_rebuild"]
        feature_rebuild_mode = "full"
        _clear_artifact_target(output_dir)
        _clear_artifact_target(meta_path)

    existing_batches = _batch_file_map(output_dir)
    existing_batch_ids = sorted(existing_batches)

    run_mode = "current"
    if feature_rebuild_mode == "full" or not existing_batch_ids:
        if config.rebuild_existing or (feature_rebuild_mode == "full" and existing_batch_ids):
            run_mode = "full_recompute"
        else:
            run_mode = "full_first_build"
        write_start_batch = combined_batch_ids[0]
        write_batch_ids = combined_batch_ids
        context_start_batch = combined_batch_ids[0]
    else:
        if not config.feature_incremental_update:
            return {
                "rows": int(sum(pl.read_parquet(path, columns=["timestamp"]).height for path in existing_batches.values())),
                "batches": int(len(existing_batch_ids)),
                "output_dir": output_dir,
                "status": "current",
                "run_mode": "current",
            }

        stale_batch_ids = [batch_id for batch_id in existing_batch_ids if batch_id not in combined_batch_set]
        for batch_id in stale_batch_ids:
            stale_path = output_dir / f"batch_{batch_id:04d}.parquet"
            stale_path.unlink(missing_ok=True)
        existing_batch_ids = [batch_id for batch_id in existing_batch_ids if batch_id in combined_batch_set]
        existing_batch_set = set(existing_batch_ids)

        missing_batch_ids = [batch_id for batch_id in combined_batch_ids if batch_id not in existing_batch_set]
        if (
            not feature_rebuild_reasons
            and not missing_batch_ids
            and existing_batch_ids
            and existing_batch_ids[-1] >= combined_max_batch
        ):
            return {
                "rows": int(sum(pl.read_parquet(path, columns=["timestamp"]).height for path in _batch_file_map(output_dir).values())),
                "batches": int(len(existing_batch_ids)),
                "output_dir": output_dir,
                "status": "current",
                "run_mode": "current",
            }

        run_mode = "incremental_tail"
        overlap_batches = config.feature_incremental_overlap_batches_by_tf.get(tf, 2)
        context_batches = config.feature_context_batches_by_tf.get(tf, 2)
        trigger_batch = min(missing_batch_ids) if missing_batch_ids else combined_max_batch
        write_start_batch = max(combined_batch_ids[0], trigger_batch - overlap_batches)
        context_start_batch = max(combined_batch_ids[0], write_start_batch - context_batches)
        write_batch_ids = [batch_id for batch_id in combined_batch_ids if batch_id >= write_start_batch]

    df_full = df_full.filter(pl.col("batch_id") >= context_start_batch)
    df_full = df_full.with_columns(pl.col("family_bar_pos").cast(pl.Int32).alias("bar_pos"))
    bars_per_batch = _bars_per_batch(regime, tf)
    print(
        f"  Feature scope {regime}/{family}/{tf}: run_mode={run_mode}, "
        f"context_start_batch={context_start_batch}, write_start_batch={write_start_batch}, "
        f"write_batches={len(write_batch_ids):,}, rows={len(df_full):,}",
        flush=True,
    )
    df_full = df_full.with_columns(
        ((pl.col("bar_pos") + 1) / bars_per_batch).alias("bar_in_batch_norm")
    )

    meta_keep_cols = [
        "timestamp",
        "batch_id",
        "period_8h_start",
        "bar_in_batch_norm",
        *[col for col in FAMILY_META_COLS if col != "period_8h_start"],
    ]
    meta_keep_cols = list(dict.fromkeys(meta_keep_cols))
    meta_df = df_full.select([col for col in meta_keep_cols if col in df_full.columns])
    bar_pos = df_full["bar_pos"].to_numpy().astype(np.int32)

    df_pd = df_full.select(["timestamp", "open", "high", "low", "close", "volume"]).to_pandas()
    del df_full
    gc.collect()

    if tf in SOURCE_AUGMENTED_FEATURE_TFS:
        print(
            f"  Augmenting {regime}/{family}/{tf} feature input with fetched auxiliary sources...",
            flush=True,
        )
        df_pd = engine.augment_dataframe_for_timeframe(df_pd, target_tf=tf)

    df_features = engine.compute_features(df=df_pd, target_tf=tf)
    distance_windows = config.distance_windows_by_tf.get(tf, {})
    if distance_windows:
        close = df_pd["close"].to_numpy()
        high = df_pd["high"].to_numpy()
        low = df_pd["low"].to_numpy()
        dist_feature_map: dict[str, np.ndarray] = {}
        for window in sorted(set(distance_windows.values())):
            d_avg_high, d_avg_low, d_top5_high, d_bot5_low = _compute_past_distance_metrics(
                close, high, low, bar_pos, window, OUTLIER_PERCENTILE
            )
            if distance_windows.get("dist_avg_high") == window:
                dist_feature_map[f"D_dist_avg_high_w{window}"] = d_avg_high
            if distance_windows.get("dist_avg_low") == window:
                dist_feature_map[f"D_dist_avg_low_w{window}"] = d_avg_low
            if distance_windows.get("dist_top5_high") == window:
                dist_feature_map[f"D_dist_top5_high_w{window}"] = d_top5_high
            if distance_windows.get("dist_bot5_low") == window:
                dist_feature_map[f"D_dist_bot5_low_w{window}"] = d_bot5_low

        if dist_feature_map:
            df_features = pd.concat([df_features, pd.DataFrame(dist_feature_map)], axis=1)

    df_features = pd.concat(
        [df_features, df_pd[["open", "high", "low", "close", "volume"]]], axis=1
    )
    df_pl = pl.from_pandas(df_features).join(meta_df, on="timestamp", how="left")

    batch_ids = sorted(df_pl["batch_id"].drop_nulls().unique().to_list())
    write_batch_set = set(write_batch_ids)
    batch_ids_to_write = [batch_id for batch_id in batch_ids if batch_id in write_batch_set]
    progress_started_at = time.time()
    for idx, batch_id in enumerate(batch_ids_to_write, 1):
        df_pl.filter(pl.col("batch_id") == batch_id).write_parquet(
            output_dir / f"batch_{int(batch_id):04d}.parquet"
        )
        _log_batch_progress(
            config,
            f"{regime}/{family}/{tf} feature batches",
            idx,
            len(batch_ids_to_write),
            started_at=progress_started_at,
        )

    _write_json(
        meta_path,
        _artifact_meta_payload(
            artifact_version=_stage_version(config, "features", family),
            family=family,
            timeframe=tf,
            source_fingerprint=feature_source_fingerprint,
            schema_columns=df_pl.columns,
            rebuild_mode=run_mode,
            extra={
                "stage": "features",
                "batch_regime": regime,
                "batch_duration_hours": int(REGIME_CONFIGS[regime].duration_hours),
                "family_shift_hours": int(0 if family == "B" else REGIME_CONFIGS[regime].shift_hours),
                "anchor_utc": _anchor_utc_str(regime),
                "entry_window_hours": int(REGIME_CONFIGS[regime].entry_window_hours),
                "rows": int(len(df_pl)),
                "batches": int(len(batch_ids)),
                "rows_per_batch": int(bars_per_batch),
                "output_dir": str(output_dir),
                "run_mode": run_mode,
                "rebuild_reasons": feature_rebuild_reasons,
                "context_start_batch": int(context_start_batch),
                "write_start_batch": int(write_start_batch),
                "write_batches_count": int(len(batch_ids_to_write)),
                "expected_rows_per_batch": int(bars_per_batch),
                "incomplete_batches_count": int(
                    len(
                        (
                            df_pl.group_by("batch_id")
                            .agg(pl.len().alias("rows"))
                            .filter(pl.col("rows") < bars_per_batch)
                        )
                    )
                ),
            },
        ),
    )
    return {
        "rows": int(len(df_pl)),
        "batches": int(len(batch_ids)),
        "output_dir": output_dir,
        "status": "created",
        "run_mode": run_mode,
        "write_start_batch": int(write_start_batch),
        "context_start_batch": int(context_start_batch),
    }


def _build_15m_metrics(
    config: MultiRegimeHTFConfig,
    regime: str,
    family: str,
) -> dict[str, Any]:
    tf = "15m"
    scope = _family_scope(config.data_dir, regime, family)
    combined_path = Path(scope["backtest"]) / f"{tf}_HTF_combined.parquet"
    output_path = Path(scope["backtest"]) / f"{tf}_distance_metrics.parquet"
    meta_path = Path(scope["backtest"]) / f"{tf}_distance_metrics_meta.json"

    df = pl.read_parquet(combined_path).sort(["batch_id", "timestamp"])
    batch_counts = df.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
    last_batch_id = int(batch_counts["batch_id"].max())
    valid_batches = batch_counts.filter(
        (pl.col("n") == _bars_per_batch(regime, tf))
        | ((pl.col("batch_id") == last_batch_id) & (pl.col("n") >= 1))
    )["batch_id"].to_list()
    metric_schema_columns = (
        pl.scan_parquet(output_path).collect_schema().names() if output_path.exists() else []
    )
    if not metric_schema_columns:
        metric_schema_columns = (_load_json_safe(meta_path) or {}).get("schema_columns", [])
    metric_rebuild_reasons, metric_rebuild_mode = _prepare_stage_rebuild(
        stage_name=f"{regime} distance metrics {family}/15m",
        meta_path=meta_path,
        artifact_version=_stage_version(config, "distance_metrics", family),
        family=family,
        timeframe=tf,
        source_fingerprint={"combined": _fingerprint_paths([combined_path])},
        schema_columns=metric_schema_columns,
        output_targets=[output_path, meta_path],
        full_rebuild_reasons={
            "missing_meta",
            "artifact_version",
            "family",
            "timeframe",
            "schema_columns",
        },
    )
    if config.rebuild_existing or metric_rebuild_mode == "full" or not output_path.exists():
        rebuild_batches = valid_batches
        run_mode = "full_recompute" if config.rebuild_existing else "full_first_build"
    elif not config.incremental_distance_metrics:
        return {
            "rows": int(pl.scan_parquet(output_path).select(pl.len()).collect().item()),
            "batches": int(len(valid_batches)),
            "status": "current",
            "run_mode": "current",
        }
    else:
        tail_n = config.incremental_distance_tail_batches_by_tf.get(tf, 8)
        existing_metric_batches = set(
            pl.read_parquet(output_path, columns=["batch_id"])["batch_id"].unique().to_list()
        )
        missing_batches = sorted(set(valid_batches) - existing_metric_batches)
        stale_batches = sorted(existing_metric_batches - set(valid_batches))
        if (
            not metric_rebuild_reasons
            and not missing_batches
            and not stale_batches
            and existing_metric_batches.issuperset(valid_batches)
        ):
            return {
                "rows": int(pl.scan_parquet(output_path).select(pl.len()).collect().item()),
                "batches": int(len(valid_batches)),
                "status": "current",
                "run_mode": "current",
            }
        tail_batches = valid_batches[-tail_n:]
        rebuild_batches = sorted(set(tail_batches) | set(missing_batches))
        run_mode = "incremental_tail"
        if not rebuild_batches:
            return {
                "rows": int(pl.scan_parquet(output_path).select(pl.len()).collect().item()),
                "batches": int(len(valid_batches)),
                "status": "current",
                "run_mode": "current",
            }
    print(
        f"  Distance metric scope {regime}/{family}/15m: run_mode={run_mode}, "
        f"rebuild_batches={len(rebuild_batches):,}/{len(valid_batches):,}",
        flush=True,
    )

    df = df.filter(pl.col("batch_id").is_in(rebuild_batches))
    df = df.with_columns(
        [
            pl.col("family_bar_pos").cast(pl.Int32).alias("bar_pos"),
            pl.col("close").rolling_mean(window_size=BB_PERIOD).alias("bb_middle"),
            pl.col("close").rolling_std(window_size=BB_PERIOD).alias("bb_std"),
        ]
    ).with_columns(
        [
            (pl.col("bb_middle") + BB_STD * pl.col("bb_std")).alias("bb_upper"),
            (pl.col("bb_middle") - BB_STD * pl.col("bb_std")).alias("bb_lower"),
        ]
    ).with_columns(
        [
            (
                (pl.col("close") - pl.col("bb_lower"))
                / (pl.col("bb_upper") - pl.col("bb_lower"))
                * 100
            ).alias("bb_position_pct"),
            (pl.col("bar_pos") // max(1, 120 // TF_MINUTES[tf])).alias("segment_2h"),
        ]
    )

    metrics = compute_distance_metrics(
        df["close"].to_numpy().astype("float64"),
        df["high"].to_numpy().astype("float64"),
        df["low"].to_numpy().astype("float64"),
        df["batch_id"].to_numpy().astype("int64"),
        df["bar_pos"].to_numpy().astype("int32"),
        _bars_per_batch(regime, tf),
        MIN_REMAINING_15M,
    )
    df = df.with_columns(
        [
            pl.Series("dist_avg_high", metrics[0]),
            pl.Series("dist_avg_low", metrics[1]),
            pl.Series("dist_top5_high", metrics[2]),
            pl.Series("dist_bot5_low", metrics[3]),
            pl.Series("remaining_bars", metrics[4]),
        ]
    )
    if run_mode == "incremental_tail" and output_path.exists():
        drop_batches = set(rebuild_batches) | set(stale_batches)
        df_prev = pl.read_parquet(output_path).filter(~pl.col("batch_id").is_in(sorted(drop_batches)))
        df_out = pl.concat([df_prev, df], how="diagonal_relaxed").sort(["batch_id", "timestamp"])
    else:
        df_out = df
    df_out.write_parquet(output_path)
    _write_json(
        meta_path,
        _artifact_meta_payload(
            artifact_version=_stage_version(config, "distance_metrics", family),
            family=family,
            timeframe=tf,
            source_fingerprint={"combined": _fingerprint_paths([combined_path])},
            schema_columns=df_out.columns,
            rebuild_mode=run_mode,
            extra={
                "stage": "distance_metrics",
                "batch_regime": regime,
                "batch_duration_hours": int(REGIME_CONFIGS[regime].duration_hours),
                "family_shift_hours": int(0 if family == "B" else REGIME_CONFIGS[regime].shift_hours),
                "anchor_utc": _anchor_utc_str(regime),
                "entry_window_hours": int(REGIME_CONFIGS[regime].entry_window_hours),
                "rows": int(len(df_out)),
                "batches": int(df_out["batch_id"].n_unique()),
                "rows_per_batch": int(_bars_per_batch(regime, tf)),
                "output_path": str(output_path),
                "rebuild_reasons": metric_rebuild_reasons,
                "updated_batches": [int(batch_id) for batch_id in rebuild_batches],
                "updated_batches_count": int(len(rebuild_batches)),
            },
        ),
    )
    return {
        "rows": int(len(df_out)),
        "batches": int(df_out["batch_id"].n_unique()),
        "status": "created",
        "run_mode": run_mode,
    }


def _build_1m_labels(
    config: MultiRegimeHTFConfig,
    regime: str,
    family: str,
) -> dict[str, Any]:
    scope = _family_scope(config.data_dir, regime, family)
    input_1m = Path(scope["backtest"]) / "1m_HTF_combined.parquet"
    input_15m = Path(scope["backtest"]) / "15m_HTF_combined.parquet"
    label_dir = Path(scope["labels"]) / "1m"
    meta_path = label_dir / "_labels_meta.json"
    label_dir.mkdir(parents=True, exist_ok=True)

    artifact_version = _stage_version(config, "labels", family)
    source_fingerprint = {
        "combined_1m": _fingerprint_paths([input_1m]),
        "combined_15m": _fingerprint_paths([input_15m]),
    }
    required_batch_columns = set(["timestamp", "batch_id", "target_4class", "target_breakfree", *FAMILY_META_COLS])

    df_1m = pl.read_parquet(input_1m).sort("timestamp")
    df_15m = pl.read_parquet(input_15m).sort("timestamp")

    counts_1m = df_1m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
    counts_15m = df_15m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
    label_batches = _eligible_label_batches_from_counts(counts_1m, counts_15m, regime)
    if not label_batches:
        return {"rows": 0, "batches": 0, "valid_labels": 0, "label_dir": label_dir, "status": "current"}

    label_output_cols = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "batch_id",
        "bar_pos_1m",
        "bar_pos_15m",
        "remaining_bars",
        "bb_upper",
        "bb_lower",
        "bb_middle",
        "bb_position_pct",
        "segment_2h",
        "dist_avg_high",
        "dist_avg_low",
        "dist_top5_high",
        "dist_bot5_low",
        "close_end",
        "end_return",
        "target_4class",
        "target_name",
        "target_breakfree",
        *FAMILY_META_COLS,
    ]
    rebuild_reasons, rebuild_mode = _prepare_stage_rebuild(
        stage_name=f"{regime} labels {family}/1m",
        meta_path=meta_path,
        artifact_version=artifact_version,
        family=family,
        timeframe="1m",
        source_fingerprint=source_fingerprint,
        schema_columns=label_output_cols,
        output_targets=[label_dir, meta_path],
        inspect_batch_dir=label_dir,
        required_batch_columns=required_batch_columns,
        full_rebuild_reasons={
            "missing_meta",
            "artifact_version",
            "family",
            "timeframe",
            "schema_columns",
            "legacy_schema",
        },
    )
    if config.rebuild_existing:
        _clear_artifact_target(label_dir)
        _clear_artifact_target(meta_path)
        rebuild_reasons = ["forced_rebuild"]
        rebuild_mode = "full"
    existing_label_files = sorted(label_dir.glob("batch_*.parquet"))
    existing_label_ids = {
        int(path.stem.split("_")[1])
        for path in existing_label_files
        if path.stem.startswith("batch_")
    }
    stale_label_ids = sorted(existing_label_ids - set(label_batches))
    for batch_id in stale_label_ids:
        (label_dir / f"batch_{batch_id:04d}.parquet").unlink(missing_ok=True)
    if stale_label_ids:
        existing_label_files = sorted(label_dir.glob("batch_*.parquet"))
        existing_label_ids = {
            int(path.stem.split("_")[1])
            for path in existing_label_files
            if path.stem.startswith("batch_")
        }
    if (
        existing_label_files
        and label_batches
        and not rebuild_reasons
        and not stale_label_ids
        and existing_label_ids.issuperset(label_batches)
        and rebuild_mode != "full"
    ):
        valid_labels = int(
            pl.scan_parquet(str(label_dir / "batch_*.parquet"))
            .filter(pl.col("target_4class") >= 0)
            .select(pl.len())
            .collect()
            .item()
        )
        return {
            "rows": int(
                pl.scan_parquet(str(label_dir / "batch_*.parquet"))
                .select(pl.len())
                .collect()
                .item()
            ),
            "batches": int(len(existing_label_ids)),
            "valid_labels": valid_labels,
            "label_dir": label_dir,
            "status": "current",
            "run_mode": "current",
        }
    if (
        config.incremental_label_update
        and existing_label_files
        and label_batches
        and rebuild_mode != "full"
        and not config.rebuild_existing
    ):
        target_batches, compute_batches, missing_batches = _select_incremental_label_batches(
            label_batches=set(label_batches),
            existing_label_files=existing_label_files,
            tail_batches=config.incremental_label_tail_batches_by_tf.get("1m", 8),
        )
        run_mode = "incremental_tail"
    else:
        target_batches = set(label_batches)
        compute_batches = set(label_batches)
        missing_batches = []
        run_mode = "full_recompute" if config.rebuild_existing else "full_first_build"
    print(
        f"  Label scope {regime}/{family}/1m: run_mode={run_mode}, "
        f"target_batches={len(target_batches):,}, compute_batches={len(compute_batches):,}, "
        "entry_bar_limit=computed_later",
        flush=True,
    )

    df_1m = df_1m.filter(pl.col("batch_id").is_in(compute_batches))
    df_15m = df_15m.filter(pl.col("batch_id").is_in(compute_batches))
    batch_close_1m = df_1m.group_by("batch_id").agg(
        pl.col("close").sort_by("timestamp").last().alias("close_end")
    )
    df_1m = df_1m.join(batch_close_1m, on="batch_id", how="left").with_columns(
        [
            ((pl.col("close_end") - pl.col("close")) / pl.col("close")).alias("end_return"),
            pl.col("family_bar_pos").cast(pl.Int32).alias("bar_pos_1m"),
            pl.col("timestamp").dt.truncate("15m").alias("ts_15m"),
        ]
    )
    df_15m = df_15m.with_columns(
        pl.col("family_bar_pos").cast(pl.Int32).alias("bar_pos_15m")
    )
    df_1m = (
        df_1m.with_columns(
            [
                pl.col("close").rolling_mean(window_size=BB_PERIOD).alias("bb_middle"),
                pl.col("close").rolling_std(window_size=BB_PERIOD).alias("bb_std"),
            ]
        )
        .with_columns(
            [
                (pl.col("bb_middle") + BB_STD * pl.col("bb_std")).alias("bb_upper"),
                (pl.col("bb_middle") - BB_STD * pl.col("bb_std")).alias("bb_lower"),
            ]
        )
        .with_columns(
            [
                (
                    (pl.col("close") - pl.col("bb_lower"))
                    / (pl.col("bb_upper") - pl.col("bb_lower"))
                    * 100
                ).alias("bb_position_pct"),
                (pl.col("bar_pos_1m") // 120).alias("segment_2h"),
            ]
        )
    )

    df_15m_pos = df_15m.select(
        [
            pl.col("timestamp").alias("ts_15m"),
            pl.col("batch_id").alias("batch_id_check"),
            "bar_pos_15m",
        ]
    )
    df_1m = df_1m.join(df_15m_pos, on="ts_15m", how="left")
    metrics = compute_hybrid_distance_metrics(
        df_1m["close"].to_numpy().astype("float64"),
        df_1m["batch_id"].to_numpy().astype("int64"),
        df_1m["bar_pos_15m"].fill_null(0).to_numpy().astype("int32"),
        df_15m["high"].to_numpy().astype("float64"),
        df_15m["low"].to_numpy().astype("float64"),
        df_15m["batch_id"].to_numpy().astype("int64"),
        df_15m["bar_pos_15m"].to_numpy().astype("int32"),
        MIN_REMAINING_15M,
        OUTLIER_PERCENTILE,
    )
    df_1m = df_1m.with_columns(
        [
            pl.Series("dist_avg_high", metrics[0]),
            pl.Series("dist_avg_low", metrics[1]),
            pl.Series("dist_top5_high", metrics[2]),
            pl.Series("dist_bot5_low", metrics[3]),
            pl.Series("remaining_bars", metrics[4]),
        ]
    )

    entry_bar_limit = _entry_bar_limit(regime, "1m")
    print(
        f"  Label gating {regime}/{family}/1m: entry_bar_limit={entry_bar_limit}, "
        f"expected_valid_rows_per_full_batch={_expected_valid_1m_rows(regime)}",
        flush=True,
    )
    df_labels = compute_4class_labels(
        df=df_1m,
        breakout_thresh=config.breakout_threshold,
        risk_thresh=config.risk_ratio,
    )
    df_labels = df_labels.with_columns(
        [
            pl.when(pl.col("target_4class") < 0)
            .then(pl.lit(-1))
            .when(
                pl.col("target_4class").is_in([2, 3])
                & (pl.col("end_return") >= config.breakfree_threshold_1m)
            )
            .then(pl.lit(0))
            .when(
                pl.col("target_4class").is_in([0, 1])
                & (pl.col("end_return") <= -config.breakfree_threshold_1m)
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(2))
            .alias("target_breakfree"),
        ]
    )
    df_labels = df_labels.with_columns(
        [
            pl.when(pl.col("bar_pos_1m") < entry_bar_limit)
            .then(pl.col("target_4class"))
            .otherwise(pl.lit(-1))
            .alias("target_4class_gated"),
            pl.when(pl.col("bar_pos_1m") < entry_bar_limit)
            .then(pl.col("target_breakfree"))
            .otherwise(pl.lit(-1))
            .alias("target_breakfree_gated"),
        ]
    ).drop(["target_4class", "target_breakfree"]).rename(
        {
            "target_4class_gated": "target_4class",
            "target_breakfree_gated": "target_breakfree",
        }
    )

    df_output = (
        df_labels.filter(pl.col("batch_id").is_in(sorted(target_batches)))
        .select([col for col in label_output_cols if col in df_labels.columns])
    )
    batch_ids = sorted(df_output["batch_id"].unique().to_list())
    progress_started_at = time.time()
    for idx, batch_id in enumerate(batch_ids, 1):
        df_output.filter(pl.col("batch_id") == batch_id).write_parquet(
            label_dir / f"batch_{int(batch_id):04d}.parquet"
        )
        _log_batch_progress(
            config,
            f"{regime}/{family}/1m label batches",
            idx,
            len(batch_ids),
            started_at=progress_started_at,
        )

    valid_labels = int(len(df_output.filter(pl.col("target_4class") >= 0)))
    _write_json(
        meta_path,
        _artifact_meta_payload(
            artifact_version=artifact_version,
            family=family,
            timeframe="1m",
            source_fingerprint=source_fingerprint,
            schema_columns=df_output.columns,
            rebuild_mode=run_mode if rebuild_mode != "full" else "full",
            extra={
                "stage": "labels",
                "batch_regime": regime,
                "batch_duration_hours": int(REGIME_CONFIGS[regime].duration_hours),
                "family_shift_hours": int(0 if family == "B" else REGIME_CONFIGS[regime].shift_hours),
                "anchor_utc": _anchor_utc_str(regime),
                "entry_window_hours": int(REGIME_CONFIGS[regime].entry_window_hours),
                "rebuild_reasons": rebuild_reasons,
                "rows": int(len(df_output)),
                "valid_labels": valid_labels,
                "updated_batches": [int(batch_id) for batch_id in batch_ids],
                "updated_batches_count": int(len(batch_ids)),
                "missing_backfill_count": int(len(missing_batches)),
                "expected_valid_rows_per_full_batch": int(_expected_valid_1m_rows(regime)),
                "run_mode": run_mode,
            },
        ),
    )
    return {
        "rows": int(len(df_output)),
        "batches": int(len(batch_ids)),
        "valid_labels": valid_labels,
        "label_dir": label_dir,
        "status": "created",
        "run_mode": run_mode,
    }


def _run_optimization(config: MultiRegimeHTFConfig, regime: str, family: str) -> dict[str, Any]:
    from scripts.feature_engineering.optimize_htf_features import (
        HTFOptimizationConfig,
        optimize_htf_features,
    )

    scope = _family_scope(config.data_dir, regime, family)
    label_dir = Path(scope["labels"]) / "1m"
    feature_dir = Path(scope["features"]) / "1m"
    if not label_dir.exists() or not feature_dir.exists():
        return {"skipped": True, "reason": "missing_inputs"}

    label_files = sorted(label_dir.glob("batch_*.parquet"))
    n_batches = len(label_files)
    n_early_batches = min(200, max(20, n_batches - 5))
    opt_config = HTFOptimizationConfig(
        project_root=config.project_root,
        htf_features_dir_override=Path(scope["features"]),
        htf_labels_dir_override=Path(scope["labels"]),
        htf_optimized_dir_override=Path(scope["optimized"]),
        timeframes=["1m"],
        targets=["target_4class"],
        n_early_batches=n_early_batches,
        n_val_folds=3,
        stability_lambda=0.5,
        save_results=True,
        recompute=config.rebuild_existing,
        incremental_update=not config.rebuild_existing,
        max_state_snapshots=32,
    )
    result = optimize_htf_features(opt_config, verbose=True)
    if isinstance(result, pd.DataFrame):
        rows = int(len(result))
    else:
        rows = int(len(pd.DataFrame(result)))
    return {"skipped": False, "result_rows": rows}


def _build_helpers(
    config: MultiRegimeHTFConfig,
    regime: str,
    family: str,
) -> dict[str, Any]:
    scope = _family_scope(config.data_dir, regime, family)
    raw_dir = Path(scope["features"]) / "1m"
    opt_dir = Path(scope["optimized"]) / "1m" / "target_4class"
    output_dir = Path(scope["helpers"]) / "1m" / "target_4class"
    meta_path = output_dir / "_helpers_meta.json"
    if not raw_dir.exists() or not opt_dir.exists():
        return {"skipped": True, "reason": "missing_inputs"}
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(raw_dir.glob("batch_*.parquet"))
    opt_files = sorted(opt_dir.glob("batch_*.parquet"))
    if not raw_files or not opt_files:
        return {"skipped": True, "reason": "missing_inputs"}
    helper_cache_raw_dir, cache_namespace = (
        _helper_cache_source(config, regime, family)
        if config.use_canonical_helper_cache
        else (raw_dir, f"{regime}_{family.lower()}")
    )
    if not helper_cache_raw_dir.exists():
        return {"skipped": True, "reason": "missing_canonical_helper_source"}

    cache_dir = _helper_cache_root(config) / cache_namespace / "1m" / "target_4class"
    cache_meta_path = cache_dir / "_helper_cache_meta.json"
    helper_contract = get_helper_contract_metadata(HELPER_NAMES)
    cache_source_fingerprint = {
        "raw_batches": _fingerprint_batch_dir(helper_cache_raw_dir),
        "helper_implementation": helper_contract["helper_implementation_fingerprint"],
    }
    cache_artifact_version = f"{config.pipeline_artifact_version}-helper-cache-v1"

    if config.use_canonical_helper_cache:
        _emit_progress(
            config,
            "detail",
            stage=f"{regime}/{family}/1m/helpers/cache",
            cache_dir=cache_dir,
            canonical_raw_dir=helper_cache_raw_dir,
        )
    cache_result = build_helper_cache_exact(
        raw_dir=helper_cache_raw_dir,
        cache_dir=cache_dir,
        meta_path=cache_meta_path,
        timeframe="1m",
        target="target_4class",
        helpers=list(HELPER_NAMES),
        warmup_rows=config.helper_warmup_by_tf["1m"],
        refit_every=config.helper_refit_every_by_tf["1m"],
        overlap_batches=config.helper_cache_overlap_batches_by_tf.get("1m", 2),
        rebuild_existing=config.rebuild_existing,
        incremental_update=config.incremental_helper_cache_update,
        artifact_version=cache_artifact_version,
        source_fingerprint=cache_source_fingerprint,
        chunk_progress_every=10,
        batch_progress_every=max(1, config.stage_progress_every_batches),
        verbose=True,
        log=print,
    )

    raw_by_id = {
        int(path.stem.split("_")[1]): path
        for path in raw_files
        if path.stem.startswith("batch_")
    }
    opt_by_id = {
        int(path.stem.split("_")[1]): path
        for path in opt_files
        if path.stem.startswith("batch_")
    }
    raw_sig = {
        "count": int(len(raw_by_id)),
        "max_batch": int(max(raw_by_id)),
        "max_mtime_ns": int(max(int(path.stat().st_mtime_ns) for path in raw_by_id.values())),
    }
    opt_sig = {
        "count": int(len(opt_by_id)),
        "max_batch": int(max(opt_by_id)),
        "max_mtime_ns": int(max(int(path.stat().st_mtime_ns) for path in opt_by_id.values())),
    }
    helper_source_fingerprint = {
        "helper_cache": _fingerprint_batch_dir(cache_dir),
        "helper_cache_meta": _fingerprint_paths([cache_meta_path]),
        "optimized_batches": _fingerprint_batch_dir(opt_dir),
        "optimized_meta": _fingerprint_paths(
            [Path(scope["optimized"]) / "1m" / "optimized_target_4class_meta.json"]
        ),
    }

    materialize_result = materialize_helpers_from_cache(
        cache_dir=cache_dir,
        optimized_dir=opt_dir,
        output_dir=output_dir,
        meta_path=meta_path,
        family=family,
        timeframe="1m",
        target="target_4class",
        overlap_batches=config.helper_overlap_batches_by_tf.get("1m", 2),
        rebuild_existing=config.rebuild_existing,
        incremental_skip_unchanged=config.incremental_helpers_skip_unchanged,
        artifact_version=_stage_version(config, "helpers", family),
        source_fingerprint=helper_source_fingerprint,
        helper_contract_version=helper_contract["helper_contract_version"],
        helper_runtime_contracts=helper_contract["helper_runtime_contracts"],
        extra_meta={
            "stage": "helpers",
            "batch_regime": regime,
            "batch_duration_hours": int(REGIME_CONFIGS[regime].duration_hours),
            "family_shift_hours": int(0 if family == "B" else REGIME_CONFIGS[regime].shift_hours),
            "anchor_utc": _anchor_utc_str(regime),
            "entry_window_hours": int(REGIME_CONFIGS[regime].entry_window_hours),
            "helper_cache_dir": str(cache_dir),
            "helper_cache_meta": str(cache_meta_path),
            "cache_run_mode": cache_result.run_mode,
            "cache_status": cache_result.status,
            "cache_namespace": cache_namespace,
            "warmup": int(config.helper_warmup_by_tf["1m"]),
            "refit_every": int(config.helper_refit_every_by_tf["1m"]),
            "raw_sig": raw_sig,
            "opt_sig": opt_sig,
            "helper_contract_version": helper_contract["helper_contract_version"],
            "helper_runtime_contracts": helper_contract["helper_runtime_contracts"],
            "helper_implementation_fingerprint": helper_contract["helper_implementation_fingerprint"],
            "write_helpers_combined": bool(config.write_helpers_combined),
        },
        write_combined=config.write_helpers_combined,
        batch_progress_every=max(1, config.stage_progress_every_batches),
        log=print,
    )
    return {
        "skipped": materialize_result.status == "current",
        "rows": int(materialize_result.rows),
        "batches": int(len(opt_by_id)),
        "status": materialize_result.status,
        "run_mode": materialize_result.run_mode,
        "cache_status": cache_result.status,
        "cache_run_mode": cache_result.run_mode,
    }


def _period_starts_match(df: pl.DataFrame, regime: str, family: str) -> int:
    if df.is_empty():
        return 0
    expected = df.select(_period_start_expr("timestamp", regime, family).alias("expected"))
    actual = df.select(pl.col("family_period_start").dt.replace_time_zone(None).alias("actual"))
    return int((actual["actual"] != expected["expected"]).sum())


def _validate_anchor(regime: str, family: str, starts: list[datetime]) -> tuple[bool, str]:
    if not starts:
        return False, "missing_starts"
    hours = {start.hour for start in starts}
    minutes = {start.minute for start in starts}
    if regime == "24h":
        expected_hour = 0 if family == "B" else 12
        ok = hours == {expected_hour} and minutes == {0}
        return ok, f"hours={sorted(hours)} minutes={sorted(minutes)} expected_hour={expected_hour}"
    if regime == "7d":
        expected_hour = 0 if family == "B" else 12
        expected_weekday = 0 if family == "B" else 3
        weekdays = {start.weekday() for start in starts}
        ok = hours == {expected_hour} and minutes == {0} and weekdays == {expected_weekday}
        return (
            ok,
            f"hours={sorted(hours)} minutes={sorted(minutes)} weekdays={sorted(weekdays)} "
            f"expected_hour={expected_hour} expected_weekday={expected_weekday}",
        )
    return True, "legacy_8h_anchor_not_validated_here"


def _validation_row(
    regime: str,
    family: str,
    tf: str,
    stage: str,
    check: str,
    ok: bool,
    detail: str,
) -> dict[str, Any]:
    return {
        "regime": regime,
        "family": family,
        "tf": tf,
        "stage": stage,
        "check": check,
        "ok": bool(ok),
        "detail": detail,
    }


def _scan_null_count(scan: pl.LazyFrame, col: str) -> int:
    return int(scan.filter(pl.col(col).is_null()).select(pl.len()).collect().item())


def _scan_duplicate_timestamp_count(scan: pl.LazyFrame) -> int:
    return int(
        scan.group_by(["batch_id", "timestamp"])
        .agg(pl.len().alias("n"))
        .filter(pl.col("n") > 1)
        .select(pl.len())
        .collect()
        .item()
    )


def _expected_prefix_status(actual_ids: list[int], expected_ids: list[int]) -> tuple[bool, str]:
    if not actual_ids:
        return len(expected_ids) == 0, "found=0"
    actual_ids = sorted(set(actual_ids))
    actual_set = set(actual_ids)
    expected_ids = sorted(set(expected_ids))
    expected_set = set(expected_ids)
    max_actual_id = actual_ids[-1]
    prefix_expected_ids = [bid for bid in expected_ids if bid <= max_actual_id]
    prefix_expected_set = set(prefix_expected_ids)
    missing_prefix_ids = sorted(prefix_expected_set - actual_set)
    trailing_missing_ids = sorted(expected_set - actual_set - set(missing_prefix_ids))
    extra_ids = sorted(actual_set - expected_set)
    ok = len(missing_prefix_ids) == 0 and len(extra_ids) == 0
    detail = (
        f"missing_prefix={len(missing_prefix_ids)} extra={len(extra_ids)} "
        f"trailing_missing={len(trailing_missing_ids)} "
        f"first_missing_prefix={missing_prefix_ids[:5]} first_extra={extra_ids[:5]}"
    )
    return ok, detail


def _nullish_count_expr(col: str, dtype: pl.DataType) -> pl.Expr:
    expr = pl.col(col).is_null()
    if dtype.is_float():
        expr = expr | pl.col(col).is_nan()
    return expr.sum().alias(col)


def _nonnull_expr(col: str, dtype: pl.DataType) -> pl.Expr:
    expr = pl.col(col)
    if dtype.is_float():
        expr = pl.when(pl.col(col).is_nan()).then(None).otherwise(pl.col(col))
    return expr


def _audit_value_columns(
    scan: pl.LazyFrame,
    schema: pl.Schema,
    columns: list[str],
    *,
    null_rate_threshold: float,
    top_n: int,
) -> dict[str, Any]:
    if not columns:
        return {
            "rows": 0,
            "columns": 0,
            "all_null_columns": [],
            "high_null_columns": [],
            "top_null_columns": [],
        }

    aggregated = scan.select(
        [pl.len().alias("__rows__")]
        + [_nullish_count_expr(col, schema[col]) for col in columns]
    ).collect()
    rows = int(aggregated["__rows__"][0]) if len(aggregated) > 0 else 0
    stats: list[dict[str, Any]] = []
    for col in columns:
        nulls = int(aggregated[col][0]) if rows >= 0 else 0
        rate = (nulls / rows) if rows > 0 else 0.0
        stats.append(
            {
                "column": col,
                "nulls": nulls,
                "rows": rows,
                "null_rate": float(rate),
            }
        )

    all_null_columns = [item for item in stats if rows > 0 and item["nulls"] == rows]
    high_null_columns = [
        item
        for item in stats
        if rows > 0 and item["null_rate"] >= float(null_rate_threshold)
    ]
    top_null_columns = sorted(
        [item for item in stats if item["nulls"] > 0],
        key=lambda item: (-item["null_rate"], -item["nulls"], item["column"]),
    )[:top_n]
    return {
        "rows": rows,
        "columns": len(columns),
        "all_null_columns": all_null_columns,
        "high_null_columns": sorted(
            high_null_columns,
            key=lambda item: (-item["null_rate"], -item["nulls"], item["column"]),
        ),
        "top_null_columns": top_null_columns,
    }


def _audit_constant_columns(
    scan: pl.LazyFrame,
    schema: pl.Schema,
    columns: list[str],
    *,
    top_n: int,
) -> dict[str, Any]:
    if not columns:
        return {
            "rows": 0,
            "columns": 0,
            "constant_columns": [],
            "top_constant_columns": [],
        }

    aggregated = scan.select(
        [pl.len().alias("__rows__")]
        + [
            _nonnull_expr(col, schema[col]).drop_nulls().n_unique().alias(col)
            for col in columns
        ]
    ).collect()
    rows = int(aggregated["__rows__"][0]) if len(aggregated) > 0 else 0
    stats: list[dict[str, Any]] = []
    for col in columns:
        unique_non_null = int(aggregated[col][0]) if rows >= 0 else 0
        stats.append(
            {
                "column": col,
                "rows": rows,
                "unique_non_null": unique_non_null,
            }
        )

    constant_columns = [
        item
        for item in stats
        if rows > 0 and item["unique_non_null"] <= 1
    ]
    constant_columns = sorted(
        constant_columns,
        key=lambda item: (item["unique_non_null"], item["column"]),
    )
    return {
        "rows": rows,
        "columns": len(columns),
        "constant_columns": constant_columns,
        "top_constant_columns": constant_columns[:top_n],
    }


def _format_usability_columns(items: list[dict[str, Any]], *, limit: int = 5) -> str:
    if not items:
        return "count=0"
    preview = ", ".join(
        f"{item['column']}:{item['null_rate']:.2%}" for item in items[:limit]
    )
    return f"count={len(items)} first={preview}"


def _format_constant_columns(items: list[dict[str, Any]], *, limit: int = 5) -> str:
    if not items:
        return "count=0"
    preview = ", ".join(
        f"{item['column']}:{item['unique_non_null']}" for item in items[:limit]
    )
    return f"count={len(items)} first={preview}"


def _format_column_names(columns: list[str], *, limit: int = 5) -> str:
    if not columns:
        return "count=0"
    preview = ", ".join(columns[:limit])
    suffix = "" if len(columns) <= limit else ", ..."
    return f"count={len(columns)} first={preview}{suffix}"


def _select_post_warmup_helper_prefix_ids(
    helper_files: list[Path],
    helper_schema_map: pl.Schema,
    helper_value_cols: list[str],
    *,
    prefix_batches: int,
) -> tuple[list[int], int | None]:
    if not helper_files or not helper_value_cols or prefix_batches <= 0:
        return [], None

    helper_ids = [
        int(path.stem.split("_")[1])
        for path in helper_files
        if path.stem.startswith("batch_")
    ]
    first_ready_index: int | None = None
    for idx, batch_path in enumerate(helper_files):
        batch_audit = _audit_value_columns(
            pl.scan_parquet(str(batch_path)),
            helper_schema_map,
            helper_value_cols,
            null_rate_threshold=1.0,
            top_n=1,
        )
        if batch_audit["rows"] > 0 and len(batch_audit["all_null_columns"]) < len(helper_value_cols):
            first_ready_index = idx
            break

    if first_ready_index is None:
        return [], None

    start_batch_id = helper_ids[first_ready_index]
    return helper_ids[first_ready_index : first_ready_index + int(prefix_batches)], start_batch_id


def _validate_regime(config: MultiRegimeHTFConfig, regime: str) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    usability_reports: list[dict[str, Any]] = []
    feature_engine = _init_feature_engine(config)
    for family in ("B", "C"):
        scope = _family_scope(config.data_dir, regime, family)
        expected_ids_by_tf: dict[str, list[int]] = {}
        counts_by_tf: dict[str, pl.DataFrame] = {}
        for tf in UPSTREAM_TIMEFRAMES:
            combined_path = Path(scope["backtest"]) / f"{tf}_HTF_combined.parquet"
            if not combined_path.exists():
                rows.append(_validation_row(regime, family, tf, "combined", "exists", False, str(combined_path)))
                continue

            combined_scan = pl.scan_parquet(str(combined_path))
            combined_schema = set(combined_scan.collect_schema().names())
            required_combined_cols = {
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "period_8h_start",
                "batch_id",
                *FAMILY_META_COLS,
            }
            missing_combined_cols = sorted(required_combined_cols - combined_schema)
            rows.append(
                _validation_row(
                    regime,
                    family,
                    tf,
                    "combined",
                    "required_columns",
                    len(missing_combined_cols) == 0,
                    "missing=" + ",".join(missing_combined_cols) if missing_combined_cols else "ok",
                )
            )

            counts = combined_scan.group_by("batch_id").agg(pl.len().alias("n")).collect().sort("batch_id")
            counts_by_tf[tf] = counts
            expected_ids = counts["batch_id"].to_list() if len(counts) > 0 else []
            expected_ids_by_tf[tf] = expected_ids
            expected_rows = _bars_per_batch(regime, tf)
            if len(counts) > 0:
                first_batch_id = int(counts["batch_id"].min())
                last_batch_id = int(counts["batch_id"].max())
                edge_batch_ids = [first_batch_id, last_batch_id]
                bad_rows = counts.filter(
                    (~pl.col("batch_id").is_in(edge_batch_ids) & (pl.col("n") != expected_rows))
                    | (pl.col("batch_id").is_in(edge_batch_ids) & (pl.col("n") > expected_rows))
                )
                rows.append(_validation_row(regime, family, tf, "combined", "rows_per_batch", len(bad_rows) == 0, f"bad_batches={len(bad_rows)} expected={expected_rows}"))
                rows.append(
                    _validation_row(
                        regime,
                        family,
                        tf,
                        "combined",
                        "batch_ids_contiguous",
                        expected_ids == list(range(expected_ids[0], expected_ids[-1] + 1)),
                        f"min={expected_ids[0]} max={expected_ids[-1]}",
                    )
                )

            if {"timestamp", "batch_id"} <= combined_schema:
                dup_ts = _scan_duplicate_timestamp_count(combined_scan)
                rows.append(_validation_row(regime, family, tf, "combined", "duplicate_timestamp_within_batch", dup_ts == 0, f"duplicates={dup_ts}"))
            for col in ["timestamp", "batch_id", "period_8h_start", "family_period_start", "family_period_end"]:
                if col in combined_schema:
                    n_null = _scan_null_count(combined_scan, col)
                    rows.append(_validation_row(regime, family, tf, "combined", f"null_{col}", n_null == 0, f"nulls={n_null}"))

            df_cols = [
                col
                for col in [
                    "timestamp",
                    "batch_id",
                    "period_8h_start",
                    "batch_family",
                    "family_batch_id",
                    "family_period_start",
                    "family_period_end",
                    "family_bar_pos",
                    "is_label_half",
                    "source_base_batch_id",
                    "source_half_in_base",
                ]
                if col in combined_schema
            ]
            df = pl.read_parquet(combined_path, columns=df_cols)

            mismatch = _period_starts_match(df, regime, family)
            rows.append(_validation_row(regime, family, tf, "combined", "period_start_alignment", mismatch == 0, f"mismatched_rows={mismatch}"))
            if {"period_8h_start", "timestamp"} <= combined_schema:
                period_mismatch = int(
                    df.select(
                        (
                            pl.col("period_8h_start").dt.replace_time_zone(None)
                            != _period_start_expr("timestamp", regime, family)
                        )
                        .sum()
                        .alias("n")
                    )["n"][0]
                )
                rows.append(_validation_row(regime, family, tf, "combined", "period_8h_start_alignment", period_mismatch == 0, f"mismatched_rows={period_mismatch}"))
            if {"family_period_start", "timestamp"} <= combined_schema:
                family_period_mismatch = int(
                    df.select(
                        (
                            pl.col("family_period_start").dt.replace_time_zone(None)
                            != _period_start_expr("timestamp", regime, family)
                        )
                        .sum()
                        .alias("n")
                    )["n"][0]
                )
                rows.append(_validation_row(regime, family, tf, "combined", "family_period_start_alignment", family_period_mismatch == 0, f"mismatched_rows={family_period_mismatch}"))
            if {"family_period_start", "family_period_end"} <= combined_schema:
                cfg = REGIME_CONFIGS[regime]
                family_end_mismatch = int(
                    df.select(
                        (
                            pl.col("family_period_end").dt.replace_time_zone(None)
                            != (
                                pl.col("family_period_start").dt.replace_time_zone(None)
                                + timedelta(hours=cfg.duration_hours)
                            )
                        )
                        .sum()
                        .alias("n")
                    )["n"][0]
                )
                rows.append(_validation_row(regime, family, tf, "combined", "family_period_end_alignment", family_end_mismatch == 0, f"mismatched_rows={family_end_mismatch}"))
            if "batch_family" in combined_schema:
                family_name_mismatch = int(df.select((pl.col("batch_family") != family).sum().alias("n"))["n"][0])
                rows.append(_validation_row(regime, family, tf, "combined", "batch_family_value", family_name_mismatch == 0, f"mismatched_rows={family_name_mismatch}"))
            if {"family_batch_id", "batch_id"} <= combined_schema:
                family_batch_mismatch = int(df.select((pl.col("family_batch_id") != pl.col("batch_id")).sum().alias("n"))["n"][0])
                rows.append(_validation_row(regime, family, tf, "combined", "family_batch_id_alignment", family_batch_mismatch == 0, f"mismatched_rows={family_batch_mismatch}"))
            if {"is_label_half", "family_bar_pos"} <= combined_schema:
                label_half_mismatch = int(
                    df.select((pl.col("is_label_half") != (pl.col("family_bar_pos") < _bars_per_half(regime, tf))).sum().alias("n"))["n"][0]
                )
                rows.append(_validation_row(regime, family, tf, "combined", "is_label_half_alignment", label_half_mismatch == 0, f"mismatched_rows={label_half_mismatch}"))
            if "family_bar_pos" in combined_schema:
                bar_pos_bounds = int(
                    df.select(
                        (
                            (pl.col("family_bar_pos") < 0)
                            | (pl.col("family_bar_pos") >= _bars_per_batch(regime, tf))
                        )
                        .sum()
                        .alias("n")
                    )["n"][0]
                )
                rows.append(_validation_row(regime, family, tf, "combined", "family_bar_pos_bounds", bar_pos_bounds == 0, f"bad_rows={bar_pos_bounds}"))

            starts = (
                df.select("family_period_start")
                .unique()
                .sort("family_period_start")["family_period_start"]
                .to_list()
            )
            anchor_ok, anchor_detail = _validate_anchor(regime, family, starts)
            rows.append(_validation_row(regime, family, tf, "combined", "anchor_alignment", anchor_ok, anchor_detail))

            feature_dir = Path(scope["features"]) / tf
            feature_files = sorted(feature_dir.glob("batch_*.parquet"))
            if not feature_files:
                rows.append(_validation_row(regime, family, tf, "features", "exists", False, str(feature_dir)))
            else:
                feature_scan = pl.scan_parquet(str(feature_dir / "batch_*.parquet"))
                feature_schema_map = feature_scan.collect_schema()
                feature_schema = set(feature_schema_map.names())
                expected_feature_cols = {
                    "timestamp",
                    *_expected_feature_schema_columns(
                        feature_engine,
                        tf,
                        config.distance_windows_by_tf.get(tf, {}),
                    ),
                }
                missing_feature_cols = sorted(expected_feature_cols - feature_schema)
                feature_counts = (
                    feature_scan.group_by("batch_id")
                    .agg(pl.len().alias("n_feature"))
                    .collect()
                    .sort("batch_id")
                )
                bad_feature_counts = (
                    counts.rename({"n": "n_combined"})
                    .join(feature_counts, on="batch_id", how="left")
                    .with_columns(pl.col("n_feature").fill_null(-1))
                    .filter(pl.col("n_combined") != pl.col("n_feature"))
                )
                feature_ids = feature_counts["batch_id"].to_list() if len(feature_counts) > 0 else []
                coverage_ok, coverage_detail = _expected_prefix_status(feature_ids, expected_ids)
                feature_value_count = len(
                    [
                        col
                        for col in feature_schema
                        if col not in {"timestamp", "batch_id", *FAMILY_META_COLS}
                    ]
                )
                rows.extend(
                    [
                        {
                            "regime": regime,
                            "family": family,
                            "tf": tf,
                            "stage": "features",
                            "check": "required_columns",
                            "ok": len(missing_feature_cols) == 0,
                            "detail": (
                                "missing=" + ",".join(missing_feature_cols)
                                if missing_feature_cols
                                else "ok"
                            ),
                        },
                        {
                            "regime": regime,
                            "family": family,
                            "tf": tf,
                            "stage": "features",
                            "check": "batch_ids_cover_expected_prefix",
                            "ok": coverage_ok,
                            "detail": coverage_detail,
                        },
                        {
                            "regime": regime,
                            "family": family,
                            "tf": tf,
                            "stage": "features",
                            "check": "rows_match_combined_counts",
                            "ok": len(bad_feature_counts) == 0,
                            "detail": f"bad_batches={len(bad_feature_counts)} expected_batches={len(expected_ids)}",
                        },
                        {
                            "regime": regime,
                            "family": family,
                            "tf": tf,
                            "stage": "features",
                            "check": "feature_columns_present",
                            "ok": feature_value_count > 0,
                            "detail": f"feature_cols={feature_value_count}",
                        },
                    ]
                )
                if {"timestamp", "batch_id"} <= feature_schema:
                    dup_ts = _scan_duplicate_timestamp_count(feature_scan)
                    rows.append(_validation_row(regime, family, tf, "features", "duplicate_timestamp_within_batch", dup_ts == 0, f"duplicates={dup_ts}"))
                for col in ["timestamp", "batch_id"]:
                    if col in feature_schema:
                        n_null = _scan_null_count(feature_scan, col)
                        rows.append(_validation_row(regime, family, tf, "features", f"null_{col}", n_null == 0, f"nulls={n_null}"))
                if config.usability_audit_enabled:
                    feature_value_cols = [
                        col
                        for col in feature_schema_map.names()
                        if col not in {"timestamp", "batch_id", *FAMILY_META_COLS}
                        and feature_schema_map[col].is_numeric()
                    ]
                    feature_audit = _audit_value_columns(
                        feature_scan,
                        feature_schema_map,
                        feature_value_cols,
                        null_rate_threshold=config.usability_audit_null_rate_threshold,
                        top_n=config.usability_audit_report_top_n,
                    )
                    usability_reports.append(
                        {
                            "regime": regime,
                            "family": family,
                            "tf": tf,
                            "stage": "features",
                            **feature_audit,
                        }
                    )
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            tf,
                            "features",
                            "usability_all_null_columns",
                            (not config.usability_audit_fail_on_all_null)
                            or len(feature_audit["all_null_columns"]) == 0,
                            _format_usability_columns(feature_audit["all_null_columns"]),
                        )
                    )
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            tf,
                            "features",
                            "usability_high_null_columns",
                            (not config.usability_audit_fail_on_high_null)
                            or len(feature_audit["high_null_columns"]) == 0,
                            _format_usability_columns(feature_audit["high_null_columns"]),
                        )
                    )

        label_dir = Path(scope["labels"]) / "1m"
        label_files = sorted(label_dir.glob("batch_*.parquet"))
        valid_counts = pl.DataFrame({"batch_id": [], "n_valid": []})
        if not label_files:
            rows.append(_validation_row(regime, family, "1m", "labels", "exists", False, str(label_dir)))
        else:
            scan = pl.scan_parquet(str(label_dir / "batch_*.parquet"))
            label_schema = set(scan.collect_schema().names())
            required_label_cols = {
                "timestamp",
                "batch_id",
                "target_4class",
                "target_breakfree",
                "bar_pos_1m",
                "bar_pos_15m",
                "remaining_bars",
                "close_end",
                *FAMILY_META_COLS,
            }
            missing_label_cols = sorted(required_label_cols - label_schema)
            rows.append(
                _validation_row(
                    regime,
                    family,
                    "1m",
                    "labels",
                    "required_columns",
                    len(missing_label_cols) == 0,
                    "missing=" + ",".join(missing_label_cols) if missing_label_cols else "ok",
                )
            )
            if {"timestamp", "batch_id"} <= label_schema:
                dup_ts = _scan_duplicate_timestamp_count(scan)
                rows.append(_validation_row(regime, family, "1m", "labels", "duplicate_timestamp_within_batch", dup_ts == 0, f"duplicates={dup_ts}"))
            for col in ["timestamp", "batch_id"]:
                if col in label_schema:
                    n_null = _scan_null_count(scan, col)
                    rows.append(_validation_row(regime, family, "1m", "labels", f"null_{col}", n_null == 0, f"nulls={n_null}"))

            valid_counts = (
                scan.group_by("batch_id")
                .agg((pl.col("target_4class") >= 0).sum().alias("n_valid"))
                .collect()
                .sort("batch_id")
            )
            label_ids = valid_counts["batch_id"].to_list() if len(valid_counts) > 0 else []
            label_expected_ids = _eligible_label_batches_from_counts(
                counts_by_tf.get("1m", pl.DataFrame({"batch_id": [], "n": []})),
                counts_by_tf.get("15m", pl.DataFrame({"batch_id": [], "n": []})),
                regime,
            )
            coverage_ok, coverage_detail = _expected_prefix_status(label_ids, label_expected_ids)
            rows.append(_validation_row(regime, family, "1m", "labels", "batch_ids_cover_expected_prefix", coverage_ok, coverage_detail))

            family_meta_required = set(FAMILY_META_COLS) - {"batch_id"}
            if family_meta_required <= label_schema:
                metadata_nulls = int(
                    scan.filter(
                        pl.any_horizontal(
                            [pl.col(col).is_null() for col in sorted(family_meta_required)]
                        )
                    )
                    .select(pl.len())
                    .collect()
                    .item()
                )
                rows.append(_validation_row(regime, family, "1m", "labels", "family_metadata_backfilled", metadata_nulls == 0, f"rows_with_missing_meta={metadata_nulls}"))
            else:
                missing_meta_cols = sorted(family_meta_required - label_schema)
                rows.append(_validation_row(regime, family, "1m", "labels", "family_metadata_backfilled", False, "missing=" + ",".join(missing_meta_cols)))

            bad_t4 = int(
                scan.filter(~pl.col("target_4class").is_in([-1, 0, 1, 2, 3]))
                .select(pl.len())
                .collect()
                .item()
            )
            bad_bf = int(
                scan.filter(~pl.col("target_breakfree").is_in([-1, 0, 1, 2]))
                .select(pl.len())
                .collect()
                .item()
            )
            rows.append(_validation_row(regime, family, "1m", "labels", "target_4class_value_range", bad_t4 == 0, f"invalid_rows={bad_t4}"))
            rows.append(_validation_row(regime, family, "1m", "labels", "target_breakfree_value_range", bad_bf == 0, f"invalid_rows={bad_bf}"))

            if len(valid_counts) > 0:
                last_batch_id = int(valid_counts["batch_id"].max())
                bad_valid = valid_counts.filter(
                    ((pl.col("batch_id") != last_batch_id) & (pl.col("n_valid") != _expected_valid_1m_rows(regime)))
                    | ((pl.col("batch_id") == last_batch_id) & (pl.col("n_valid") > _expected_valid_1m_rows(regime)))
                )
                rows.append(
                    {
                        "regime": regime,
                        "family": family,
                        "tf": "1m",
                        "stage": "labels",
                        "check": "valid_rows_per_batch",
                        "ok": len(bad_valid) == 0,
                        "detail": f"bad_batches={len(bad_valid)} expected={_expected_valid_1m_rows(regime)}",
                    }
                )

            remaining_violations = int(
                scan.filter(
                    pl.col("remaining_bars")
                    > (_bars_per_batch(regime, "15m") - pl.col("bar_pos_15m") - 1)
                )
                .select(pl.len())
                .collect()
                .item()
            )
            rows.append(
                {
                    "regime": regime,
                    "family": family,
                    "tf": "1m",
                    "stage": "labels",
                    "check": "remaining_bars_within_batch",
                    "ok": remaining_violations == 0,
                    "detail": f"violations={remaining_violations}",
                }
            )
            invalid_pair = int(
                scan.filter((pl.col("target_4class") < 0) & (pl.col("target_breakfree") != -1))
                .select(pl.len())
                .collect()
                .item()
            )
            rows.append(
                _validation_row(
                    regime,
                    family,
                    "1m",
                    "labels",
                    "breakfree_invalid_when_4class_invalid",
                    invalid_pair == 0,
                    f"violations={invalid_pair}",
                )
            )
            entry_limit = _bars_per_half(regime, "1m")
            late_labels = int(
                scan.filter((pl.col("bar_pos_1m") >= entry_limit) & (pl.col("target_4class") >= 0))
                .select(pl.len())
                .collect()
                .item()
            )
            rows.append(_validation_row(regime, family, "1m", "labels", "entry_window_gating_4class", late_labels == 0, f"late_labeled_rows={late_labels}"))

            combined_1m = pl.read_parquet(
                Path(scope["backtest"]) / "1m_HTF_combined.parquet",
                columns=["batch_id", "timestamp", "close"],
            )
            batch_close = combined_1m.group_by("batch_id").agg(
                pl.col("close").sort_by("timestamp").last().alias("close_ref")
            )
            sample = (
                pl.read_parquet(label_files[0], columns=["batch_id", "close_end"])
                .join(batch_close, on="batch_id", how="left")
            )
            close_mismatch = int((sample["close_end"] != sample["close_ref"]).sum())
            rows.append(
                {
                    "regime": regime,
                    "family": family,
                    "tf": "1m",
                    "stage": "labels",
                    "check": "breakfree_uses_batch_end_close",
                    "ok": close_mismatch == 0,
                    "detail": f"mismatched_rows={close_mismatch}",
                }
            )

        opt_dir = Path(scope["optimized"]) / "1m" / "target_4class"
        opt_files = sorted(opt_dir.glob("batch_*.parquet"))
        if config.run_optimization or opt_files:
            if not opt_files:
                rows.append(_validation_row(regime, family, "1m", "optimized", "exists", False, str(opt_dir)))
            else:
                opt_scan = pl.scan_parquet(str(opt_dir / "batch_*.parquet"))
                opt_schema_map = opt_scan.collect_schema()
                opt_schema = set(opt_schema_map.names())
                missing_opt_cols = sorted({"timestamp", "batch_id", *FAMILY_META_COLS} - opt_schema)
                opt_counts = (
                    opt_scan.group_by("batch_id")
                    .agg(pl.len().alias("n_opt"))
                    .collect()
                    .sort("batch_id")
                )
                opt_ids = opt_counts["batch_id"].to_list() if len(opt_counts) > 0 else []
                expected_opt_ids = (
                    valid_counts.filter(pl.col("n_valid") > 0)["batch_id"].to_list()
                    if len(valid_counts) > 0
                    else []
                )
                coverage_ok, coverage_detail = _expected_prefix_status(opt_ids, expected_opt_ids)
                bad_opt_counts = (
                    valid_counts.join(opt_counts, on="batch_id", how="left")
                    .with_columns(pl.col("n_opt").fill_null(0))
                    .filter(
                        ((pl.col("n_valid") > 0) & (pl.col("n_valid") != pl.col("n_opt")))
                        | ((pl.col("n_valid") == 0) & (pl.col("n_opt") > 0))
                    )
                )
                rows.extend(
                    [
                        {
                            "regime": regime,
                            "family": family,
                            "tf": "1m",
                            "stage": "optimized",
                            "check": "required_columns",
                            "ok": len(missing_opt_cols) == 0,
                            "detail": (
                                "missing=" + ",".join(missing_opt_cols)
                                if missing_opt_cols
                                else "ok"
                            ),
                        },
                        {
                            "regime": regime,
                            "family": family,
                            "tf": "1m",
                            "stage": "optimized",
                            "check": "batch_ids_cover_expected_prefix",
                            "ok": coverage_ok,
                            "detail": coverage_detail,
                        },
                        {
                            "regime": regime,
                            "family": family,
                            "tf": "1m",
                            "stage": "optimized",
                            "check": "rows_match_label_valid_counts",
                            "ok": len(bad_opt_counts) == 0,
                            "detail": f"bad_batches={len(bad_opt_counts)}",
                        },
                    ]
                )
                if {"timestamp", "batch_id"} <= opt_schema:
                    dup_ts = _scan_duplicate_timestamp_count(opt_scan)
                    rows.append(_validation_row(regime, family, "1m", "optimized", "duplicate_timestamp_within_batch", dup_ts == 0, f"duplicates={dup_ts}"))
                for col in ["timestamp", "batch_id"]:
                    if col in opt_schema:
                        n_null = _scan_null_count(opt_scan, col)
                        rows.append(_validation_row(regime, family, "1m", "optimized", f"null_{col}", n_null == 0, f"nulls={n_null}"))
                policy_blocked_opt_cols = get_final_output_excluded_columns(
                    opt_schema_map.names(),
                    stage="optimized",
                )
                rows.append(
                    _validation_row(
                        regime,
                        family,
                        "1m",
                        "optimized",
                        "policy_excluded_columns_absent",
                        len(policy_blocked_opt_cols) == 0,
                        _format_column_names(policy_blocked_opt_cols),
                    )
                )
                if config.usability_audit_enabled:
                    opt_value_cols = [
                        col
                        for col in opt_schema_map.names()
                        if col not in {"timestamp", "batch_id", *FAMILY_META_COLS}
                        and opt_schema_map[col].is_numeric()
                    ]
                    opt_audit = _audit_value_columns(
                        opt_scan,
                        opt_schema_map,
                        opt_value_cols,
                        null_rate_threshold=config.usability_audit_null_rate_threshold,
                        top_n=config.usability_audit_report_top_n,
                    )
                    usability_reports.append(
                        {
                            "regime": regime,
                            "family": family,
                            "tf": "1m",
                            "stage": "optimized",
                            **opt_audit,
                        }
                    )
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            "1m",
                            "optimized",
                            "usability_all_null_columns",
                            (not config.usability_audit_fail_on_all_null)
                            or len(opt_audit["all_null_columns"]) == 0,
                            _format_usability_columns(opt_audit["all_null_columns"]),
                        )
                    )
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            "1m",
                            "optimized",
                            "usability_high_null_columns",
                            (not config.usability_audit_fail_on_high_null)
                            or len(opt_audit["high_null_columns"]) == 0,
                            _format_usability_columns(opt_audit["high_null_columns"]),
                        )
                    )

        helper_dir = Path(scope["helpers"]) / "1m" / "target_4class"
        helper_meta_path = helper_dir / "_helpers_meta.json"
        helper_files = sorted(helper_dir.glob("batch_*.parquet"))
        if config.run_helpers or helper_files:
            helper_contract_current = get_helper_contract_metadata(HELPER_NAMES)
            helper_meta = _load_json_safe(helper_meta_path)
            rows.append(
                _validation_row(
                    regime,
                    family,
                    "1m",
                    "helpers",
                    "meta_exists",
                    helper_meta is not None,
                    str(helper_meta_path),
                )
            )
            if helper_meta is not None:
                rows.append(
                    _validation_row(
                        regime,
                        family,
                        "1m",
                        "helpers",
                        "helper_policy_version_match",
                        helper_meta.get("helper_policy_version") == FINAL_OUTPUT_FEATURE_POLICY_VERSION,
                        (
                            f"expected={FINAL_OUTPUT_FEATURE_POLICY_VERSION} "
                            f"actual={helper_meta.get('helper_policy_version')}"
                        ),
                    )
                )
                rows.append(
                    _validation_row(
                        regime,
                        family,
                        "1m",
                        "helpers",
                        "helper_contract_version_match",
                        helper_meta.get("helper_contract_version")
                        == helper_contract_current["helper_contract_version"],
                        (
                            f"expected={helper_contract_current['helper_contract_version']} "
                            f"actual={helper_meta.get('helper_contract_version')}"
                        ),
                    )
                )
                rows.append(
                    _validation_row(
                        regime,
                        family,
                        "1m",
                        "helpers",
                        "helper_runtime_contracts_match",
                        helper_meta.get("helper_runtime_contracts")
                        == helper_contract_current["helper_runtime_contracts"],
                        (
                            f"expected={json.dumps(helper_contract_current['helper_runtime_contracts'], sort_keys=True)} "
                            f"actual={json.dumps(helper_meta.get('helper_runtime_contracts'), sort_keys=True)}"
                        ),
                    )
                )
                rows.append(
                    _validation_row(
                        regime,
                        family,
                        "1m",
                        "helpers",
                        "helper_implementation_fingerprint_match",
                        helper_meta.get("helper_implementation_fingerprint")
                        == helper_contract_current["helper_implementation_fingerprint"],
                        (
                            f"expected={helper_contract_current['helper_implementation_fingerprint']['digest'][:12]} "
                            f"actual={(helper_meta.get('helper_implementation_fingerprint') or {}).get('digest', 'missing')[:12]}"
                        ),
                    )
                )
                helper_cache_meta_path_str = helper_meta.get("helper_cache_meta")
                helper_cache_meta_path = (
                    Path(helper_cache_meta_path_str) if helper_cache_meta_path_str else None
                )
                helper_cache_meta = (
                    _load_json_safe(helper_cache_meta_path)
                    if helper_cache_meta_path is not None
                    else None
                )
                rows.append(
                    _validation_row(
                        regime,
                        family,
                        "1m",
                        "helpers",
                        "helper_cache_meta_exists",
                        helper_cache_meta is not None,
                        str(helper_cache_meta_path) if helper_cache_meta_path is not None else "missing",
                    )
                )
                if helper_cache_meta is not None:
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            "1m",
                            "helpers",
                            "helper_cache_contract_version_match",
                            helper_cache_meta.get("helper_contract_version")
                            == helper_contract_current["helper_contract_version"],
                            (
                                f"expected={helper_contract_current['helper_contract_version']} "
                                f"actual={helper_cache_meta.get('helper_contract_version')}"
                            ),
                        )
                    )
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            "1m",
                            "helpers",
                            "helper_cache_runtime_contracts_match",
                            helper_cache_meta.get("helper_runtime_contracts")
                            == helper_contract_current["helper_runtime_contracts"],
                            (
                                f"expected={json.dumps(helper_contract_current['helper_runtime_contracts'], sort_keys=True)} "
                                f"actual={json.dumps(helper_cache_meta.get('helper_runtime_contracts'), sort_keys=True)}"
                            ),
                        )
                    )
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            "1m",
                            "helpers",
                            "helper_cache_implementation_fingerprint_match",
                            helper_cache_meta.get("helper_implementation_fingerprint")
                            == helper_contract_current["helper_implementation_fingerprint"],
                            (
                                f"expected={helper_contract_current['helper_implementation_fingerprint']['digest'][:12]} "
                                f"actual={(helper_cache_meta.get('helper_implementation_fingerprint') or {}).get('digest', 'missing')[:12]}"
                            ),
                        )
                    )
            if not helper_files:
                rows.append(_validation_row(regime, family, "1m", "helpers", "exists", False, str(helper_dir)))
            else:
                helper_scan = pl.scan_parquet(str(helper_dir / "batch_*.parquet"))
                helper_schema_map = helper_scan.collect_schema()
                helper_schema = set(helper_schema_map.names())
                missing_helper_cols = sorted({"timestamp", "batch_id", *FAMILY_META_COLS} - helper_schema)
                helper_counts = (
                    helper_scan.group_by("batch_id")
                    .agg(pl.len().alias("n_helper"))
                    .collect()
                    .sort("batch_id")
                )
                helper_ids = helper_counts["batch_id"].to_list() if len(helper_counts) > 0 else []
                helper_col_count = len([col for col in helper_schema if col.startswith("H_")])
                if opt_files:
                    opt_counts = (
                        pl.scan_parquet(str(opt_dir / "batch_*.parquet"))
                        .group_by("batch_id")
                        .agg(pl.len().alias("n_opt"))
                        .collect()
                        .sort("batch_id")
                    )
                    bad_helper_counts = (
                        opt_counts.join(helper_counts, on="batch_id", how="left")
                        .with_columns(pl.col("n_helper").fill_null(-1))
                        .filter(pl.col("n_opt") != pl.col("n_helper"))
                    )
                else:
                    bad_helper_counts = helper_counts.filter(pl.lit(False))
                    opt_counts = pl.DataFrame({"batch_id": [], "n_opt": []})
                expected_helper_ids = opt_counts["batch_id"].to_list() if len(opt_counts) > 0 else []
                coverage_ok, coverage_detail = _expected_prefix_status(helper_ids, expected_helper_ids)
                rows.extend(
                    [
                        {
                            "regime": regime,
                            "family": family,
                            "tf": "1m",
                            "stage": "helpers",
                            "check": "required_columns",
                            "ok": len(missing_helper_cols) == 0,
                            "detail": (
                                "missing=" + ",".join(missing_helper_cols)
                                if missing_helper_cols
                                else "ok"
                            ),
                        },
                        {
                            "regime": regime,
                            "family": family,
                            "tf": "1m",
                            "stage": "helpers",
                            "check": "batch_ids_cover_expected_prefix",
                            "ok": coverage_ok,
                            "detail": coverage_detail,
                        },
                        {
                            "regime": regime,
                            "family": family,
                            "tf": "1m",
                            "stage": "helpers",
                            "check": "helper_columns_present",
                            "ok": helper_col_count > 0,
                            "detail": f"helper_cols={helper_col_count}",
                        },
                        {
                            "regime": regime,
                            "family": family,
                            "tf": "1m",
                            "stage": "helpers",
                            "check": "rows_match_optimized_counts",
                            "ok": len(bad_helper_counts) == 0,
                            "detail": f"bad_batches={len(bad_helper_counts)}",
                        },
                    ]
                )
                if {"timestamp", "batch_id"} <= helper_schema:
                    dup_ts = _scan_duplicate_timestamp_count(helper_scan)
                    rows.append(_validation_row(regime, family, "1m", "helpers", "duplicate_timestamp_within_batch", dup_ts == 0, f"duplicates={dup_ts}"))
                for col in ["timestamp", "batch_id"]:
                    if col in helper_schema:
                        n_null = _scan_null_count(helper_scan, col)
                        rows.append(_validation_row(regime, family, "1m", "helpers", f"null_{col}", n_null == 0, f"nulls={n_null}"))
                policy_blocked_helper_cols = get_final_output_excluded_columns(
                    helper_schema_map.names(),
                    stage="helpers",
                )
                rows.append(
                    _validation_row(
                        regime,
                        family,
                        "1m",
                        "helpers",
                        "policy_excluded_columns_absent",
                        len(policy_blocked_helper_cols) == 0,
                        _format_column_names(policy_blocked_helper_cols),
                    )
                )
                if config.usability_audit_enabled:
                    helper_model_value_cols = [
                        col
                        for col in helper_schema_map.names()
                        if col not in {"timestamp", "batch_id", *FAMILY_META_COLS}
                        and helper_schema_map[col].is_numeric()
                    ]
                    helper_value_cols = [
                        col
                        for col in helper_schema_map.names()
                        if col.startswith("H_") and helper_schema_map[col].is_numeric()
                    ]
                    helper_model_audit = _audit_value_columns(
                        helper_scan,
                        helper_schema_map,
                        helper_model_value_cols,
                        null_rate_threshold=config.usability_audit_null_rate_threshold,
                        top_n=config.usability_audit_report_top_n,
                    )
                    usability_reports.append(
                        {
                            "regime": regime,
                            "family": family,
                            "tf": "1m",
                            "stage": "helpers",
                            **helper_model_audit,
                        }
                    )
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            "1m",
                            "helpers",
                            "usability_all_null_columns",
                            (not config.usability_audit_fail_on_all_null)
                            or len(helper_model_audit["all_null_columns"]) == 0,
                            _format_usability_columns(helper_model_audit["all_null_columns"]),
                        )
                    )
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            "1m",
                            "helpers",
                            "usability_high_null_columns",
                            (not config.usability_audit_fail_on_high_null)
                            or len(helper_model_audit["high_null_columns"]) == 0,
                            _format_usability_columns(helper_model_audit["high_null_columns"]),
                        )
                    )
                    helper_audit = _audit_value_columns(
                        helper_scan,
                        helper_schema_map,
                        helper_value_cols,
                        null_rate_threshold=config.usability_audit_null_rate_threshold,
                        top_n=config.usability_audit_report_top_n,
                    )
                    usability_reports.append(
                        {
                            "regime": regime,
                            "family": family,
                            "tf": "1m",
                            "stage": "helpers_helper_only",
                            **helper_audit,
                        }
                    )
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            "1m",
                            "helpers",
                            "usability_all_null_helper_columns",
                            (not config.usability_audit_fail_on_all_null)
                            or len(helper_audit["all_null_columns"]) == 0,
                            _format_usability_columns(helper_audit["all_null_columns"]),
                        )
                    )
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            "1m",
                            "helpers",
                            "usability_high_null_helper_columns",
                            (not config.usability_audit_fail_on_high_null)
                            or len(helper_audit["high_null_columns"]) == 0,
                            _format_usability_columns(helper_audit["high_null_columns"]),
                        )
                    )
                    helper_constant_audit = _audit_constant_columns(
                        helper_scan,
                        helper_schema_map,
                        helper_value_cols,
                        top_n=config.usability_audit_report_top_n,
                    )
                    usability_reports.append(
                        {
                            "regime": regime,
                            "family": family,
                            "tf": "1m",
                            "stage": "helpers_helper_only_constant",
                            **helper_constant_audit,
                        }
                    )
                    rows.append(
                        _validation_row(
                            regime,
                            family,
                            "1m",
                            "helpers",
                            "usability_constant_helper_columns",
                            (not config.usability_audit_fail_on_constant)
                            or len(helper_constant_audit["constant_columns"]) == 0,
                            _format_constant_columns(helper_constant_audit["constant_columns"]),
                        )
                    )
                    helper_post_warmup_prefix_ids, first_ready_helper_batch = (
                        _select_post_warmup_helper_prefix_ids(
                            helper_files,
                            helper_schema_map,
                            helper_value_cols,
                            prefix_batches=config.usability_audit_helper_prefix_batches,
                        )
                    )
                    if helper_value_cols and first_ready_helper_batch is None:
                        rows.append(
                            _validation_row(
                                regime,
                                family,
                                "1m",
                                "helpers",
                                "usability_post_warmup_prefix_available",
                                False,
                                "no_helper_batches_with_non_null_helper_values_found",
                            )
                        )
                    if helper_post_warmup_prefix_ids and helper_value_cols:
                        helper_prefix_audit = _audit_value_columns(
                            helper_scan.filter(pl.col("batch_id").is_in(helper_post_warmup_prefix_ids)),
                            helper_schema_map,
                            helper_value_cols,
                            null_rate_threshold=config.usability_audit_null_rate_threshold,
                            top_n=config.usability_audit_report_top_n,
                        )
                        usability_reports.append(
                            {
                                "regime": regime,
                                "family": family,
                                "tf": "1m",
                                "stage": "helpers_post_warmup_prefix",
                                "first_ready_batch": int(first_ready_helper_batch),
                                "prefix_batches": [
                                    int(batch_id) for batch_id in helper_post_warmup_prefix_ids
                                ],
                                **helper_prefix_audit,
                            }
                        )
                        rows.append(
                            _validation_row(
                                regime,
                                family,
                                "1m",
                                "helpers",
                                "usability_post_warmup_prefix_all_null_helper_columns",
                                (not config.usability_audit_fail_on_all_null)
                                or len(helper_prefix_audit["all_null_columns"]) == 0,
                                _format_usability_columns(helper_prefix_audit["all_null_columns"]),
                            )
                        )

    base_scope = _family_scope(config.data_dir, regime, "B")
    shift_scope = _family_scope(config.data_dir, regime, "C")
    b_path = Path(base_scope["backtest"]) / "1m_HTF_combined.parquet"
    c_path = Path(shift_scope["backtest"]) / "1m_HTF_combined.parquet"
    if b_path.exists() and c_path.exists():
        half = _bars_per_half(regime, "1m")
        b = pl.read_parquet(
            b_path,
            columns=["timestamp", "batch_id", "family_bar_pos", "is_label_half"],
        )
        c = pl.read_parquet(
            c_path,
            columns=[
                "timestamp",
                "batch_id",
                "family_bar_pos",
                "source_base_batch_id",
                "source_half_in_base",
                "is_label_half",
            ],
        )
        b_counts = b.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
        c_counts = c.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
        complete_b_ids = b_counts.filter(pl.col("n") == _bars_per_batch(regime, "1m"))["batch_id"].to_list()
        complete_c_ids = c_counts.filter(pl.col("n") == _bars_per_batch(regime, "1m"))["batch_id"].to_list()
        c_complete = c.filter(pl.col("batch_id").is_in(complete_c_ids))
        c_first = c_complete.filter(pl.col("family_bar_pos") < half)
        c_second = c_complete.filter(pl.col("family_bar_pos") >= half)
        bad_source_first = c_first.filter(
            (pl.col("source_base_batch_id") != pl.col("batch_id"))
            | (pl.col("source_half_in_base") != "F")
        )
        bad_source_second = c_second.filter(
            (pl.col("source_base_batch_id") != (pl.col("batch_id") + 1))
            | (pl.col("source_half_in_base") != "L")
        )
        rows.extend(
            [
                _validation_row(
                    regime,
                    "B+C",
                    "1m",
                    "cross_family",
                    "c_first_half_source_mapping",
                    len(bad_source_first) == 0,
                    f"bad_rows={len(bad_source_first)}",
                ),
                _validation_row(
                    regime,
                    "B+C",
                    "1m",
                    "cross_family",
                    "c_second_half_source_mapping",
                    len(bad_source_second) == 0,
                    f"bad_rows={len(bad_source_second)}",
                ),
            ]
        )
        b_second = b.filter(pl.col("family_bar_pos") >= half).select(
            ["timestamp", pl.col("batch_id").alias("c_batch_id")]
        )
        c_first_join = c_first.select(["timestamp", pl.col("batch_id").alias("c_batch_id")])
        missing_first = c_first_join.join(b_second, on=["timestamp", "c_batch_id"], how="anti")
        b_first_next = (
            b.filter(pl.col("family_bar_pos") < half)
            .select(["timestamp", (pl.col("batch_id") - 1).alias("c_batch_id")])
            .filter(pl.col("c_batch_id") > 0)
        )
        c_second_join = c_second.select(["timestamp", pl.col("batch_id").alias("c_batch_id")])
        missing_second = c_second_join.join(b_first_next, on=["timestamp", "c_batch_id"], how="anti")
        rows.extend(
            [
                _validation_row(
                    regime,
                    "B+C",
                    "1m",
                    "cross_family",
                    "c_first_half_equals_b_second_half",
                    len(missing_first) == 0,
                    f"missing_rows={len(missing_first)}",
                ),
                _validation_row(
                    regime,
                    "B+C",
                    "1m",
                    "cross_family",
                    "c_second_half_equals_next_b_first_half",
                    len(missing_second) == 0,
                    f"missing_rows={len(missing_second)}",
                ),
            ]
        )

        expected_valid = pl.concat(
            [
                b.filter(pl.col("batch_id").is_in(complete_b_ids) & pl.col("is_label_half")).select("timestamp"),
                c.filter(pl.col("batch_id").is_in(complete_c_ids) & pl.col("is_label_half")).select("timestamp"),
            ],
            how="vertical",
        ).unique()

        b_label_dir = Path(base_scope["labels"]) / "1m"
        c_label_dir = Path(shift_scope["labels"]) / "1m"
        if b_label_dir.exists() and c_label_dir.exists():
            b_valid = (
                pl.scan_parquet(str(b_label_dir / "batch_*.parquet"))
                .filter(pl.col("batch_id").is_in(complete_b_ids) & (pl.col("target_4class") >= 0))
                .select("timestamp")
                .collect()
                .unique()
            )
            c_valid = (
                pl.scan_parquet(str(c_label_dir / "batch_*.parquet"))
                .filter(pl.col("batch_id").is_in(complete_c_ids) & (pl.col("target_4class") >= 0))
                .select("timestamp")
                .collect()
                .unique()
            )
            dup_valid = b_valid.join(c_valid, on="timestamp", how="inner")
            actual_valid = pl.concat([b_valid, c_valid], how="vertical").unique()
            missing_valid = expected_valid.join(actual_valid, on="timestamp", how="anti")
            extra_valid = actual_valid.join(expected_valid, on="timestamp", how="anti")
            rows.extend(
                [
                    _validation_row(
                        regime,
                        "B+C",
                        "1m",
                        "cross_family",
                        "no_overlap_in_valid_labels",
                        len(dup_valid) == 0,
                        f"duplicate_valid_rows={len(dup_valid)}",
                    ),
                    _validation_row(
                        regime,
                        "B+C",
                        "1m",
                        "cross_family",
                        "expected_valid_coverage",
                        len(missing_valid) == 0 and len(extra_valid) == 0,
                        f"missing={len(missing_valid)} extra={len(extra_valid)}",
                    ),
                ]
            )

    if config.usability_audit_enabled and usability_reports:
        audit_dir = config.project_root / "test_output" / "htf_validation_usability"
        audit_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            audit_dir / f"{regime}_latest.json",
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "regime": regime,
                "null_rate_threshold": float(config.usability_audit_null_rate_threshold),
                "report_top_n": int(config.usability_audit_report_top_n),
                "helper_prefix_batches": int(config.usability_audit_helper_prefix_batches),
                "reports": usability_reports,
            },
        )

    return pl.DataFrame(rows)


def run_multi_regime_htf_pipeline(config: MultiRegimeHTFConfig) -> dict[str, Any]:
    pipeline_started_at = time.time()
    print("=" * 70, flush=True)
    print("[HTF] MULTI-REGIME PIPELINE START", flush=True)
    print(
        f"[HTF] build_regimes={config.build_regimes} | "
        f"validate_regimes={config.effective_validate_regimes()} | "
        f"run_optimization={config.run_optimization} | "
        f"run_helpers={config.run_helpers} | "
        f"run_validation={config.run_validation}",
        flush=True,
    )
    print("=" * 70, flush=True)
    _emit_progress(
        config,
        "start",
        stage="pipeline",
        build_regimes=config.build_regimes,
        validate_regimes=config.effective_validate_regimes(),
        run_optimization=config.run_optimization,
        run_helpers=config.run_helpers,
        run_validation=config.run_validation,
    )
    engine = _init_feature_engine(config)
    summary: dict[str, Any] = {"build": [], "validation": None}

    for regime in config.build_regimes:
        print("\n" + "=" * 70, flush=True)
        print(f"[HTF] REGIME START: {regime}", flush=True)
        print("=" * 70, flush=True)
        _emit_progress(config, "start", stage=f"{regime}/regime", regime=regime)
        regime_summary: dict[str, Any] = {"regime": regime, "families": {}}
        for tf in UPSTREAM_TIMEFRAMES:
            started_at = _log_stage_start(
                config,
                regime=regime,
                family="B",
                tf=tf,
                stage="combined",
            )
            base_info = _build_base_combined(config, regime, tf)
            _log_stage_done(
                config,
                started_at,
                regime=regime,
                family="B",
                tf=tf,
                stage="combined",
                result=base_info,
            )
            started_at = _log_stage_start(
                config,
                regime=regime,
                family="C",
                tf=tf,
                stage="combined",
            )
            shift_info = _build_shifted_combined(config, regime, tf)
            _log_stage_done(
                config,
                started_at,
                regime=regime,
                family="C",
                tf=tf,
                stage="combined",
                result=shift_info,
            )
            regime_summary.setdefault("combined", {})[tf] = {
                "B": base_info,
                "C": shift_info,
            }

        for family in ("B", "C"):
            print(f"\n[HTF] FAMILY START: regime={regime} family={family}", flush=True)
            _emit_progress(config, "start", stage=f"{regime}/{family}/family", regime=regime, family=family)
            family_summary: dict[str, Any] = {}
            for tf in UPSTREAM_TIMEFRAMES:
                started_at = _log_stage_start(
                    config,
                    regime=regime,
                    family=family,
                    tf=tf,
                    stage="features",
                )
                feature_result = _build_feature_batches(
                    config=config,
                    engine=engine,
                    regime=regime,
                    family=family,
                    tf=tf,
                )
                _log_stage_done(
                    config,
                    started_at,
                    regime=regime,
                    family=family,
                    tf=tf,
                    stage="features",
                    result=feature_result,
                )
                family_summary.setdefault("features", {})[tf] = feature_result
            started_at = _log_stage_start(
                config,
                regime=regime,
                family=family,
                tf="15m",
                stage="distance_metrics",
            )
            family_summary["metrics_15m"] = _build_15m_metrics(
                config=config,
                regime=regime,
                family=family,
            )
            _log_stage_done(
                config,
                started_at,
                regime=regime,
                family=family,
                tf="15m",
                stage="distance_metrics",
                result=family_summary["metrics_15m"],
            )
            started_at = _log_stage_start(
                config,
                regime=regime,
                family=family,
                tf="1m",
                stage="labels",
            )
            family_summary["labels_1m"] = _build_1m_labels(
                config=config,
                regime=regime,
                family=family,
            )
            _log_stage_done(
                config,
                started_at,
                regime=regime,
                family=family,
                tf="1m",
                stage="labels",
                result=family_summary["labels_1m"],
            )
            if config.run_optimization:
                started_at = _log_stage_start(
                    config,
                    regime=regime,
                    family=family,
                    tf="1m",
                    stage="optimization",
                )
                family_summary["optimization"] = _run_optimization(
                    config=config,
                    regime=regime,
                    family=family,
                )
                _log_stage_done(
                    config,
                    started_at,
                    regime=regime,
                    family=family,
                    tf="1m",
                    stage="optimization",
                    result=family_summary["optimization"],
                )
            if config.run_helpers:
                started_at = _log_stage_start(
                    config,
                    regime=regime,
                    family=family,
                    tf="1m",
                    stage="helpers",
                )
                family_summary["helpers"] = _build_helpers(
                    config=config,
                    regime=regime,
                    family=family,
                )
                _log_stage_done(
                    config,
                    started_at,
                    regime=regime,
                    family=family,
                    tf="1m",
                    stage="helpers",
                    result=family_summary["helpers"],
                )
            regime_summary["families"][family] = family_summary
            _emit_progress(config, "done", stage=f"{regime}/{family}/family", regime=regime, family=family)
        summary["build"].append(regime_summary)
        _emit_progress(config, "done", stage=f"{regime}/regime", regime=regime)

    if config.run_validation:
        validation_started_at = _log_stage_start(
            config,
            regime="all",
            family=None,
            tf=None,
            stage="validation",
            detail=f"regimes={config.effective_validate_regimes()}",
        )
        validation_frames = [
            _validate_regime(config, regime) for regime in config.effective_validate_regimes()
        ]
        validation_df = (
            pl.concat(validation_frames, how="vertical")
            if validation_frames
            else pl.DataFrame({"regime": [], "family": [], "tf": [], "stage": [], "check": [], "ok": [], "detail": []})
        )
        summary["validation"] = validation_df
        _log_stage_done(
            config,
            validation_started_at,
            regime="all",
            family=None,
            tf=None,
            stage="validation",
            result={"rows": int(len(validation_df)), "failures": int(len(validation_df.filter(~pl.col("ok"))))},
        )
        if len(validation_df) > 0:
            failed = validation_df.filter(~pl.col("ok"))
            if len(failed) > 0:
                raise AssertionError(
                    "Multi-regime HTF validation failed:\n"
                    + failed.select(["regime", "family", "tf", "stage", "check", "detail"]).to_pandas().to_string(index=False)
                )

    pipeline_elapsed = time.time() - pipeline_started_at
    print("=" * 70, flush=True)
    print(
        f"[HTF] MULTI-REGIME PIPELINE DONE | elapsed={_format_elapsed(pipeline_elapsed)}",
        flush=True,
    )
    print("=" * 70, flush=True)
    _emit_progress(
        config,
        "done",
        stage="pipeline",
        elapsed_seconds=round(pipeline_elapsed, 3),
    )
    return summary
