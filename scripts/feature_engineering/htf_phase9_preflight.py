from __future__ import annotations

"""Read-only Phase 9 preflight for HTF richer-feature schema promotion.

This probe inspects the current production HTF artifact trees and reports:
- current on-disk stage status
- expected stage status if the shared multi-regime pipeline is run now

It is intentionally read-only:
- no calls to destructive rebuild helpers
- no artifact clears
- no pipeline materialization

The preflight is meant to answer: if we start Phase 9 now, which stages will
stay current and which ones will rebuild because of the enriched 1m/15m feature
schema and its downstream dependencies?
"""

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any

import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.feature_engineering.htf_helper_cache import (
    _collect_batch_ranges,
    _meta_rebuild_reasons as helper_meta_rebuild_reasons,
    batch_file_map as helper_batch_file_map,
    helper_cols_from_batch_dir,
    overlapping_cache_batch_ids,
)
from scripts.feature_engineering.htf_multiregime_pipeline import (
    COMBINED_OUTPUT_COLS,
    FAMILY_META_COLS,
    MultiRegimeHTFConfig,
    _artifact_rebuild_reasons,
    _bars_per_batch,
    _batch_file_map,
    _expected_feature_schema_columns,
    _family_scope,
    _feature_source_fingerprint,
    _find_batch_missing_required_columns,
    _fingerprint_batch_dir,
    _fingerprint_paths,
    _helper_cache_root,
    _helper_cache_source,
    _init_feature_engine,
    _raw_dir_for_tf,
    _stage_version,
)
from scripts.feature_engineering.htf_shared_config import (
    SHARED_DISTANCE_WINDOWS_BY_TF,
    SHARED_PIPELINE_ARTIFACT_VERSION,
    SHARED_THRESHOLDS_BY_TF,
)
from scripts.feature_engineering.optimize_htf_features import (
    HTFOptimizationConfig,
    _batch_id_from_stem,
    _file_fingerprint,
    _load_transformer_state,
)

FULL_REBUILD_FEATURE_KEYS = {
    "missing_meta",
    "artifact_version",
    "family",
    "timeframe",
    "schema_columns",
    "legacy_schema",
}
FULL_REBUILD_LABEL_KEYS = {
    "missing_meta",
    "artifact_version",
    "family",
    "timeframe",
    "schema_columns",
    "legacy_schema",
}
FULL_REBUILD_HELPER_CACHE_KEYS = {
    "missing_meta",
    "artifact_version",
    "timeframe",
    "target",
    "helper_names",
    "schema_columns",
}
FULL_REBUILD_HELPER_OUTPUT_KEYS = {
    "missing_meta",
    "artifact_version",
    "family",
    "timeframe",
    "target",
    "schema_columns",
}
HELPER_NAMES = ["ou", "garch", "cusum", "kalman", "egarch"]


def _reason_key(reason: str) -> str:
    return "legacy_schema" if reason.startswith("legacy_schema:") else reason


def _batch_ids_from_combined(path: Path) -> list[int]:
    if not path.exists():
        return []
    df = pl.read_parquet(path, columns=["batch_id"])
    return sorted(df["batch_id"].drop_nulls().unique().to_list())


def _combined_base_status(config: MultiRegimeHTFConfig, regime: str, tf: str) -> dict[str, Any]:
    raw_dir = _raw_dir_for_tf(config, tf)
    scope = _family_scope(config.data_dir, regime, "B")
    output_path = Path(scope["backtest"]) / f"{tf}_HTF_combined.parquet"
    if not output_path.exists():
        return {"status": "missing_output"}
    if not raw_dir.exists() or not list(raw_dir.glob("*.parquet")):
        return {"status": "current_no_raw" if output_path.exists() else "missing_raw"}

    output_cols = set(pl.scan_parquet(str(output_path)).collect_schema().names())
    required_schema_ok = set(COMBINED_OUTPUT_COLS).issubset(output_cols)

    raw_scan = pl.scan_parquet(raw_dir / "*.parquet").with_columns(
        pl.col("timestamp").dt.replace_time_zone(None).alias("ts_norm")
    )
    if config.date_start is not None:
        raw_scan = raw_scan.filter(pl.col("ts_norm") >= config.date_start)
    if config.date_end is not None:
        raw_scan = raw_scan.filter(pl.col("ts_norm") < config.date_end)

    raw_max_ts = raw_scan.select(pl.col("timestamp").max().alias("max_ts")).collect()["max_ts"].item()
    out_max_ts = (
        pl.scan_parquet(str(output_path))
        .select(pl.col("timestamp").max().alias("max_ts"))
        .collect()["max_ts"]
        .item()
    )

    status = "current"
    reason = "up_to_date"
    if not required_schema_ok:
        status = "full_recompute"
        reason = "schema_columns"
    else:
        raw_cmp = raw_max_ts.replace(tzinfo=None) if getattr(raw_max_ts, "tzinfo", None) else raw_max_ts
        out_cmp = out_max_ts.replace(tzinfo=None) if getattr(out_max_ts, "tzinfo", None) else out_max_ts
        if raw_cmp is not None and out_cmp is not None and raw_cmp > out_cmp:
            hours_diff = (raw_cmp - out_cmp).total_seconds() / 3600.0
            if hours_diff >= float(config.min_raw_lead_hours_for_update):
                status = "full_recompute"
                reason = f"new_data (+{hours_diff:.1f}h)"

    return {
        "status": status,
        "reason": reason,
        "required_schema_ok": required_schema_ok,
    }


def _combined_shift_status(config: MultiRegimeHTFConfig, regime: str, tf: str) -> dict[str, Any]:
    base_scope = _family_scope(config.data_dir, regime, "B")
    shift_scope = _family_scope(config.data_dir, regime, "C")
    base_path = Path(base_scope["backtest"]) / f"{tf}_HTF_combined.parquet"
    base_meta_path = Path(base_scope["backtest"]) / f"{tf}_HTF_combined_meta.json"
    output_path = Path(shift_scope["backtest"]) / f"{tf}_HTF_combined.parquet"
    meta_path = Path(shift_scope["backtest"]) / f"{tf}_HTF_combined_meta.json"

    source_fingerprint = {
        "base_combined": _fingerprint_paths([base_path, base_meta_path]),
    }
    reasons = _artifact_rebuild_reasons(
        meta_path=meta_path,
        artifact_version=_stage_version(config, "combined", "C"),
        family="C",
        timeframe=tf,
        source_fingerprint=source_fingerprint,
        schema_columns=COMBINED_OUTPUT_COLS,
    )
    existing_cols = (
        set(pl.scan_parquet(str(output_path)).collect_schema().names())
        if output_path.exists()
        else set()
    )
    if output_path.exists() and existing_cols and not set(COMBINED_OUTPUT_COLS).issubset(existing_cols):
        reasons.append("schema_columns")

    return {
        "status": "current" if output_path.exists() and not reasons else ("full_recompute" if reasons else "missing_output"),
        "reasons": reasons,
    }


def _feature_status(
    config: MultiRegimeHTFConfig,
    engine,
    regime: str,
    family: str,
    tf: str,
) -> dict[str, Any]:
    scope = _family_scope(config.data_dir, regime, family)
    output_dir = Path(scope["features"]) / tf
    meta_path = output_dir / "_build_meta.json"
    combined_path = Path(scope["backtest"]) / f"{tf}_HTF_combined.parquet"
    combined_batch_ids = _batch_ids_from_combined(combined_path)

    if family == "C":
        source_scope = _family_scope(config.data_dir, regime, "B")
        source_dir = Path(source_scope["features"]) / tf
        sample_files = sorted(source_dir.glob("batch_*.parquet"))
        expected_schema = (
            pl.scan_parquet(str(sample_files[0])).collect_schema().names() if sample_files else []
        )
        source_fingerprint = {
            "base_features": _fingerprint_batch_dir(source_dir),
            "shift_combined": _fingerprint_paths(
                [combined_path, Path(scope["backtest"]) / f"{tf}_HTF_combined_meta.json"]
            ),
        }
        required_columns = {"timestamp", "batch_id", *FAMILY_META_COLS}
    else:
        expected_schema = _expected_feature_schema_columns(
            engine,
            tf,
            config.distance_windows_by_tf.get(tf, {}),
        )
        source_fingerprint = _feature_source_fingerprint(config, engine, combined_path, tf)
        required_columns = set(expected_schema)

    reasons = _artifact_rebuild_reasons(
        meta_path=meta_path,
        artifact_version=_stage_version(config, "features", family),
        family=family,
        timeframe=tf,
        source_fingerprint=source_fingerprint,
        schema_columns=expected_schema,
    )
    legacy = _find_batch_missing_required_columns(output_dir, required_columns)
    if legacy is not None:
        reasons.append(
            f"legacy_schema:{legacy['path']} missing={','.join(legacy['missing'])}"
        )

    existing_batch_ids = sorted(_batch_file_map(output_dir))
    missing_batch_ids = [bid for bid in combined_batch_ids if bid not in set(existing_batch_ids)]
    full_rebuild = any(_reason_key(r) in FULL_REBUILD_FEATURE_KEYS for r in reasons)

    if existing_batch_ids and not reasons and not missing_batch_ids:
        status = "current"
    elif existing_batch_ids:
        status = "full_recompute" if full_rebuild else "incremental_tail"
    else:
        status = "full_first_build"

    current_schema = (
        pl.scan_parquet(str(sorted(output_dir.glob("batch_*.parquet"))[0])).collect_schema().names()
        if list(output_dir.glob("batch_*.parquet"))
        else []
    )
    return {
        "status": status,
        "reasons": reasons,
        "missing_batches": len(missing_batch_ids),
        "current_schema_count": len(current_schema),
        "expected_schema_count": len(expected_schema),
    }


def _label_status(config: MultiRegimeHTFConfig, regime: str, family: str) -> dict[str, Any]:
    scope = _family_scope(config.data_dir, regime, family)
    input_1m = Path(scope["backtest"]) / "1m_HTF_combined.parquet"
    input_15m = Path(scope["backtest"]) / "15m_HTF_combined.parquet"
    label_dir = Path(scope["labels"]) / "1m"
    meta_path = label_dir / "_labels_meta.json"

    source_fingerprint = {
        "combined_1m": _fingerprint_paths([input_1m]),
        "combined_15m": _fingerprint_paths([input_15m]),
    }

    counts_1m = (
        pl.read_parquet(input_1m, columns=["batch_id"])
        .group_by("batch_id")
        .agg(pl.len().alias("n"))
        .sort("batch_id")
    )
    counts_15m = (
        pl.read_parquet(input_15m, columns=["batch_id"])
        .group_by("batch_id")
        .agg(pl.len().alias("n"))
        .sort("batch_id")
    )
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
    label_batches = sorted(set(valid_1m) & set(valid_15m))

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
    reasons = _artifact_rebuild_reasons(
        meta_path=meta_path,
        artifact_version=_stage_version(config, "labels", family),
        family=family,
        timeframe="1m",
        source_fingerprint=source_fingerprint,
        schema_columns=label_output_cols,
    )
    legacy = _find_batch_missing_required_columns(
        label_dir,
        {"timestamp", "batch_id", "target_4class", "target_breakfree", *FAMILY_META_COLS},
    )
    if legacy is not None:
        reasons.append(
            f"legacy_schema:{legacy['path']} missing={','.join(legacy['missing'])}"
        )

    existing_ids = sorted(_batch_file_map(label_dir))
    stale_ids = sorted(set(existing_ids) - set(label_batches))
    full_rebuild = any(_reason_key(r) in FULL_REBUILD_LABEL_KEYS for r in reasons)

    if existing_ids and not reasons and not stale_ids and set(existing_ids).issuperset(label_batches):
        status = "current"
    elif existing_ids:
        status = "full_recompute" if full_rebuild else "incremental_tail"
    else:
        status = "full_first_build"

    return {
        "status": status,
        "reasons": reasons,
        "stale_batches": len(stale_ids),
        "expected_batches": len(label_batches),
    }


def _optimizer_current_status(config: MultiRegimeHTFConfig, regime: str, family: str) -> dict[str, Any]:
    scope = _family_scope(config.data_dir, regime, family)
    opt_cfg = HTFOptimizationConfig(
        project_root=config.project_root,
        htf_features_dir_override=Path(scope["features"]),
        htf_labels_dir_override=Path(scope["labels"]),
        htf_optimized_dir_override=Path(scope["optimized"]),
        timeframes=["1m"],
        targets=["target_4class"],
        save_results=False,
        recompute=False,
        incremental_update=True,
    )

    features_dir = opt_cfg.htf_features_dir / "1m"
    labels_dir = opt_cfg.htf_labels_dir / "1m"
    output_dir = opt_cfg.htf_optimized_dir / "1m" / "target_4class"
    meta_file = opt_cfg.htf_optimized_dir / "1m" / "optimized_target_4class_meta.json"

    feature_files = sorted(features_dir.glob("batch_*.parquet"))
    label_files = sorted(labels_dir.glob("batch_*.parquet"))
    label_by_stem = {f.stem: f for f in label_files}
    pairs: list[dict[str, Any]] = []
    for feat_file in feature_files:
        label_file = label_by_stem.get(feat_file.stem)
        if label_file is None:
            continue
        pairs.append(
            {
                "batch_id": _batch_id_from_stem(feat_file.stem),
                "feature_file": feat_file,
                "label_file": label_file,
            }
        )
    pairs = sorted(pairs, key=lambda x: x["batch_id"])
    if not pairs:
        return {"status": "missing_inputs"}

    current_fingerprints = {
        str(rec["batch_id"]): {
            "feature": _file_fingerprint(rec["feature_file"]),
            "label": _file_fingerprint(rec["label_file"]),
        }
        for rec in pairs
    }
    output_files = {
        _batch_id_from_stem(p.stem): p
        for p in sorted(output_dir.glob("batch_*.parquet"))
    }
    cached_meta = json.loads(meta_file.read_text()) if meta_file.exists() else None
    if cached_meta is None:
        return {"status": "full_recompute", "reason": "missing_meta"}

    prev_fps = cached_meta.get("batch_fingerprints", {})
    first_diff = None
    for rec in pairs:
        batch_id = int(rec["batch_id"])
        batch_key = str(batch_id)
        out_ok = batch_id in output_files and output_files[batch_id].exists()
        if (
            batch_key not in prev_fps
            or prev_fps[batch_key] != current_fingerprints[batch_key]
            or not out_ok
        ):
            first_diff = batch_id
            break

    if first_diff is None:
        return {"status": "current", "reason": "already_up_to_date"}

    state_dir = output_dir / "_state"
    best_config = cached_meta.get("config") or {}
    start_batch = pairs[0]["batch_id"]
    resume_reason = f"full_recompute_from_{start_batch}_first_diff_{first_diff}"
    if state_dir.exists() and best_config:
        snapshot_candidates: list[tuple[int, Path]] = []
        for path in sorted(state_dir.glob("state_after_batch_*.npz")):
            try:
                snap_bid = _batch_id_from_stem(path.stem.replace("state_after_", ""))
            except Exception:
                continue
            if snap_bid < first_diff:
                snapshot_candidates.append((snap_bid, path))
        snapshot_candidates = sorted(snapshot_candidates, key=lambda x: x[0], reverse=True)
        for snap_bid, snap_path in snapshot_candidates:
            try:
                _, _, loaded_window = _load_transformer_state(snap_path)
                if int(loaded_window) != int(best_config["window"]):
                    continue
                start_batch = snap_bid + 1
                resume_reason = f"resume_from_snapshot_batch_{snap_bid}"
                break
            except Exception:
                continue

    return {
        "status": "incremental_tail" if start_batch > pairs[0]["batch_id"] else "full_recompute",
        "reason": resume_reason,
        "first_diff_batch": int(first_diff),
        "start_batch": int(start_batch),
    }


def _helper_cache_current_status(config: MultiRegimeHTFConfig, regime: str, family: str) -> dict[str, Any]:
    raw_dir, namespace = _helper_cache_source(config, regime, family)
    cache_dir = _helper_cache_root(config) / namespace / "1m" / "target_4class"
    meta_path = cache_dir / "_helper_cache_meta.json"

    raw_by_id = helper_batch_file_map(raw_dir)
    cache_by_id = helper_batch_file_map(cache_dir)
    if not raw_by_id:
        return {"status": "missing_inputs", "namespace": namespace}

    raw_mtime = {bid: int(path.stat().st_mtime_ns) for bid, path in raw_by_id.items()}
    cache_mtime = {bid: int(path.stat().st_mtime_ns) for bid, path in cache_by_id.items()}
    source_fingerprint = {"raw_batches": _fingerprint_batch_dir(raw_dir)}
    schema_columns = helper_cols_from_batch_dir(cache_dir)
    if schema_columns:
        schema_columns = ["timestamp", *schema_columns]
    else:
        schema_columns = (
            json.loads(meta_path.read_text()).get("schema_columns", [])
            if meta_path.exists()
            else []
        )

    reasons = helper_meta_rebuild_reasons(
        meta_path=meta_path,
        artifact_version=f"{config.pipeline_artifact_version}-helper-cache-v1",
        expected_fields={
            "timeframe": "1m",
            "target": "target_4class",
            "helper_names": list(HELPER_NAMES),
            "warmup": int(config.helper_warmup_by_tf["1m"]),
            "refit_every": int(config.helper_refit_every_by_tf["1m"]),
        },
        source_fingerprint=source_fingerprint,
        schema_columns=schema_columns,
    )
    full_rebuild = any(_reason_key(r) in FULL_REBUILD_HELPER_CACHE_KEYS for r in reasons)

    affected_batches: list[int] = []
    if full_rebuild or config.rebuild_existing:
        affected_batches = sorted(raw_by_id)
    else:
        for batch_id in sorted(raw_by_id):
            cache_stamp = cache_mtime.get(batch_id)
            if cache_stamp is None or cache_stamp < raw_mtime[batch_id]:
                affected_batches.append(batch_id)

    status = "current" if not affected_batches and not reasons else ("full_recompute" if full_rebuild else "incremental_tail")
    return {
        "status": status,
        "namespace": namespace,
        "reasons": reasons,
        "affected_batches": len(affected_batches),
    }


def _helper_output_current_status(config: MultiRegimeHTFConfig, regime: str, family: str) -> dict[str, Any]:
    scope = _family_scope(config.data_dir, regime, family)
    output_dir = Path(scope["helpers"]) / "1m" / "target_4class"
    meta_path = output_dir / "_helpers_meta.json"
    opt_dir = Path(scope["optimized"]) / "1m" / "target_4class"
    _, namespace = _helper_cache_source(config, regime, family)
    cache_dir = _helper_cache_root(config) / namespace / "1m" / "target_4class"
    cache_meta_path = cache_dir / "_helper_cache_meta.json"

    cache_cols = helper_cols_from_batch_dir(cache_dir)
    if not cache_cols:
        return {"status": "missing_cache", "namespace": namespace}
    opt_by_id = helper_batch_file_map(opt_dir)
    if not opt_by_id:
        return {"status": "missing_optimized", "namespace": namespace}

    output_by_id = helper_batch_file_map(output_dir)
    output_mtime = {bid: int(path.stat().st_mtime_ns) for bid, path in output_by_id.items()}
    opt_mtime = {bid: int(path.stat().st_mtime_ns) for bid, path in opt_by_id.items()}
    cache_mtime = {
        bid: int(path.stat().st_mtime_ns) for bid, path in helper_batch_file_map(cache_dir).items()
    }
    output_schema_columns = (
        pl.scan_parquet(str(sorted(output_dir.glob("batch_*.parquet"))[0])).collect_schema().names()
        if list(output_dir.glob("batch_*.parquet"))
        else (
            json.loads(meta_path.read_text()).get("schema_columns", [])
            if meta_path.exists()
            else []
        )
    )
    source_fingerprint = {
        "helper_cache": _fingerprint_batch_dir(cache_dir),
        "helper_cache_meta": _fingerprint_paths([cache_meta_path]),
        "optimized_batches": _fingerprint_batch_dir(opt_dir),
        "optimized_meta": _fingerprint_paths(
            [Path(scope["optimized"]) / "1m" / "optimized_target_4class_meta.json"]
        ),
    }
    reasons = helper_meta_rebuild_reasons(
        meta_path=meta_path,
        artifact_version=_stage_version(config, "helpers", family),
        expected_fields={
            "family": family,
            "timeframe": "1m",
            "target": "target_4class",
        },
        source_fingerprint=source_fingerprint,
        schema_columns=output_schema_columns,
    )
    full_rebuild = any(_reason_key(r) in FULL_REBUILD_HELPER_OUTPUT_KEYS for r in reasons)

    cache_ranges = _collect_batch_ranges(cache_dir)
    affected_batches: list[int] = []
    for batch_id in sorted(opt_by_id):
        opt_batch = pl.read_parquet(opt_by_id[batch_id], columns=["timestamp"])
        overlapping_ids = overlapping_cache_batch_ids(opt_batch, cache_ranges)
        if not overlapping_ids:
            return {
                "status": "error",
                "namespace": namespace,
                "reason": f"no overlapping cache for batch {batch_id}",
            }
        cache_stamp = max(cache_mtime.get(src_id, 0) for src_id in overlapping_ids)
        output_stamp = output_mtime.get(batch_id)
        if full_rebuild or output_stamp is None or output_stamp < max(opt_mtime[batch_id], cache_stamp):
            affected_batches.append(batch_id)

    status = "current" if not affected_batches and not reasons else ("full_recompute" if full_rebuild else "incremental_tail")
    return {
        "status": status,
        "namespace": namespace,
        "reasons": reasons,
        "affected_batches": len(affected_batches),
    }


def _count_statuses(section: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in section.values():
        if isinstance(item, dict) and all(isinstance(v, dict) and "status" in v for v in item.values()):
            for subitem in item.values():
                counts[subitem["status"]] = counts.get(subitem["status"], 0) + 1
        elif isinstance(item, dict) and "status" in item:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts


def _promote_feature_status_for_upstream_refresh(
    current_status: str,
    *,
    requires_full_rebuild: bool,
) -> str:
    if current_status == "full_first_build":
        return "full_first_build"
    if current_status in {"missing_inputs", "missing_source_features"}:
        return "full_first_build"
    if current_status == "full_recompute":
        return "full_recompute"
    if requires_full_rebuild:
        return "full_recompute"
    return "incremental_tail"


def build_preflight_summary(project_root: Path) -> dict[str, Any]:
    warnings.filterwarnings("ignore")
    config = MultiRegimeHTFConfig(
        project_root=project_root,
        data_dir=project_root / "data",
        raw_data_dir=project_root / "fetchingByBit",
        pipeline_artifact_version=SHARED_PIPELINE_ARTIFACT_VERSION,
        thresholds_by_tf=SHARED_THRESHOLDS_BY_TF,
        distance_windows_by_tf=SHARED_DISTANCE_WINDOWS_BY_TF,
    )
    engine = _init_feature_engine(config)

    combined_current: dict[str, Any] = {}
    feature_current: dict[str, Any] = {}
    label_current: dict[str, Any] = {}
    optimizer_current: dict[str, Any] = {}
    helper_cache_current: dict[str, Any] = {}
    helper_output_current: dict[str, Any] = {}

    for regime in ("8h", "24h", "7d"):
        for family in ("B", "C"):
            family_key = f"{regime}/{family}"
            combined_current[family_key] = {}
            for tf in ("1m", "15m"):
                combined_current[family_key][tf] = (
                    _combined_base_status(config, regime, tf)
                    if family == "B"
                    else _combined_shift_status(config, regime, tf)
                )
            feature_current[family_key] = {
                tf: _feature_status(config, engine, regime, family, tf)
                for tf in ("1m", "15m")
            }
            label_current[family_key] = _label_status(config, regime, family)
            optimizer_current[family_key] = _optimizer_current_status(config, regime, family)
            helper_cache_current[family_key] = _helper_cache_current_status(config, regime, family)
            helper_output_current[family_key] = _helper_output_current_status(config, regime, family)

    expected = {
        "combined": combined_current,
        "features": {},
        "labels": {},
        "optimized": {},
        "helper_cache": {},
        "helpers": {},
    }

    for regime in ("8h", "24h", "7d"):
        for family in ("B", "C"):
            family_key = f"{regime}/{family}"
            expected["features"][family_key] = {}

            for tf in ("1m", "15m"):
                current = feature_current[family_key][tf]
                reasons = list(current.get("reasons", []))
                status = current["status"]
                expected_schema_count = current.get("expected_schema_count")

                combined_dirty = combined_current[family_key][tf]["status"] != "current"
                if combined_dirty:
                    status = _promote_feature_status_for_upstream_refresh(
                        current["status"],
                        requires_full_rebuild=(family == "C"),
                    )
                    reasons.append("upstream_combined_refresh")

                if family == "C":
                    base_feature_key = f"{regime}/B"
                    base_feature_status = expected["features"][base_feature_key][tf]["status"]
                    if base_feature_status != "current":
                        status = _promote_feature_status_for_upstream_refresh(
                            status,
                            requires_full_rebuild=True,
                        )
                        expected_schema_count = expected["features"][base_feature_key][tf].get(
                            "expected_schema_count",
                            expected_schema_count,
                        )
                        reasons.append("upstream_base_feature_refresh")

                expected["features"][family_key][tf] = {
                    **current,
                    "status": status,
                    "reasons": reasons,
                    "expected_schema_count": expected_schema_count,
                }

            label_upstream_dirty = any(
                combined_current[family_key][tf]["status"] != "current"
                for tf in ("1m", "15m")
            )
            current_label = label_current[family_key]
            if label_upstream_dirty:
                label_status = "incremental_tail" if current_label["status"] == "current" else current_label["status"]
                label_reasons = list(current_label.get("reasons", [])) + ["upstream_combined_refresh"]
            else:
                label_status = current_label["status"]
                label_reasons = list(current_label.get("reasons", []))
            expected["labels"][family_key] = {
                **current_label,
                "status": label_status,
                "reasons": label_reasons,
            }

            current_opt = optimizer_current[family_key]
            if expected["features"][family_key]["1m"]["status"] != "current" or expected["labels"][family_key]["status"] != "current":
                expected["optimized"][family_key] = {
                    **current_opt,
                    "status": "incremental_tail" if current_opt.get("status") == "current" else current_opt.get("status", "incremental_tail"),
                    "reason": "upstream_feature_or_label_refresh",
                }
            else:
                expected["optimized"][family_key] = current_opt

            current_cache = helper_cache_current[family_key]
            raw_feature_source_status = (
                expected["features"]["8h/B"]["1m"]["status"]
                if family == "B"
                else expected["features"][family_key]["1m"]["status"]
            )
            if raw_feature_source_status != "current":
                expected["helper_cache"][family_key] = {
                    **current_cache,
                    "status": "incremental_tail" if current_cache.get("status") == "current" else current_cache.get("status", "incremental_tail"),
                    "reasons": list(current_cache.get("reasons", [])) + ["upstream_feature_refresh"],
                }
            else:
                expected["helper_cache"][family_key] = current_cache

            current_helper = helper_output_current[family_key]
            if (
                expected["optimized"][family_key].get("status") != "current"
                or expected["helper_cache"][family_key].get("status") != "current"
            ):
                expected["helpers"][family_key] = {
                    **current_helper,
                    "status": "incremental_tail" if current_helper.get("status") == "current" else current_helper.get("status", "incremental_tail"),
                    "reasons": list(current_helper.get("reasons", [])) + ["upstream_optimized_or_cache_refresh"],
                }
            else:
                expected["helpers"][family_key] = current_helper

    return {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "current_disk": {
            "combined": combined_current,
            "features": feature_current,
            "labels": label_current,
            "optimized": optimizer_current,
            "helper_cache": helper_cache_current,
            "helpers": helper_output_current,
        },
        "expected_run": expected,
        "counts": {stage: _count_statuses(expected[stage]) for stage in expected},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )
    args = parser.parse_args()

    summary = build_preflight_summary(args.project_root.resolve())
    output_path = args.output
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
