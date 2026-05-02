from __future__ import annotations

import gc
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd
import polars as pl
from scripts.feature_engineering.htf_feature_acceptance import (
    FINAL_OUTPUT_FEATURE_POLICY_VERSION,
    get_final_output_excluded_columns,
)

LogFn = Callable[[str], None]

DEFAULT_HELPER_NAMES = ("ou", "garch", "cusum", "kalman", "egarch")
HELPER_CONTRACT_VERSION = "2026-04-13-live-safe-helper-contract-v1"
HELPER_RUNTIME_CONTRACTS: dict[str, str] = {
    "cusum": "context_replay_v1",
    "garch": "context_replay_v1",
    "ou": "context_replay_v1",
    "kalman": "streaming_handoff_v1",
    "egarch": "streaming_handoff_v1",
}
HELPER_SOURCE_FILE_MAP: dict[str, tuple[str, ...]] = {
    "cusum": (
        "scripts/target_models/helpers/cusum.py",
        "riskyield_rust/src/cusum.rs",
    ),
    "garch": (
        "scripts/target_models/helpers/garch.py",
        "riskyield_rust/src/garch.rs",
    ),
    "ou": (
        "scripts/target_models/helpers/ou.py",
        "riskyield_rust/src/ou.rs",
    ),
    "kalman": (
        "scripts/target_models/helpers/kalman.py",
        "riskyield_rust/src/kalman.rs",
        "riskyield_rust/src/lib.rs",
    ),
    "egarch": (
        "scripts/target_models/helpers/egarch.py",
        "riskyield_rust/src/egarch.rs",
        "riskyield_rust/src/lib.rs",
    ),
}
# The current helper set tops out at EGARCH(126). When a helper is fitted on a
# train prefix and then transformed on a prediction chunk, we prepend one
# trailing helper-window of context to keep chunk-start features causal and
# closer to live parity without reading future rows. See the 2026-04-12 helper
# source-backed audit note for the design rationale.
HELPER_TRANSFORM_CONTEXT_ROWS = 126
HELPER_RAW_SOURCE_COLUMNS = ("timestamp", "batch_id", "close", "open", "high", "low", "volume")


@dataclass(frozen=True)
class HelperCacheBuildResult:
    cache_dir: Path
    meta_path: Path
    run_mode: str
    rows: int
    helper_cols: int
    saved_batches: int
    skipped_batches: int
    affected_batches_count: int
    write_batches_count: int
    first_affected_batch: int | None
    write_start_batch: int | None
    start_row: int | None
    status: str


@dataclass(frozen=True)
class HelperMaterializationResult:
    output_dir: Path
    meta_path: Path
    run_mode: str
    rows: int
    helper_cols: int
    saved_batches: int
    skipped_batches: int
    affected_batches_count: int
    write_batches_count: int
    first_affected_batch: int | None
    write_start_batch: int | None
    status: str


def load_json_safe(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)


def fingerprint_paths(paths: Sequence[Path]) -> dict[str, Any]:
    entries: list[tuple[str, int, int]] = []
    digest = hashlib.sha256()
    for path in sorted({Path(p) for p in paths}, key=lambda p: str(p)):
        if not path.exists():
            continue
        stat = path.stat()
        rel = str(path)
        entries.append((rel, int(stat.st_mtime_ns), int(stat.st_size)))
        digest.update(f"{rel}|{stat.st_mtime_ns}|{stat.st_size}".encode("utf-8"))
    return {
        "count": int(len(entries)),
        "latest_mtime_ns": int(max((entry[1] for entry in entries), default=0)),
        "total_size_bytes": int(sum(entry[2] for entry in entries)),
        "digest": digest.hexdigest(),
    }


def fingerprint_batch_dir(directory: Path) -> dict[str, Any]:
    return fingerprint_paths(sorted(directory.glob("batch_*.parquet")))


def schema_columns_for_batch_dir(directory: Path) -> list[str]:
    files = sorted(directory.glob("batch_*.parquet"))
    if not files:
        return []
    return pl.scan_parquet(str(files[0])).collect_schema().names()


def batch_file_map(directory: Path) -> dict[int, Path]:
    return {
        int(path.stem.split("_")[1]): path
        for path in sorted(directory.glob("batch_*.parquet"))
        if path.stem.startswith("batch_")
    }


def helper_cols_from_batch_dir(batch_dir: Path) -> list[str]:
    return [col for col in schema_columns_for_batch_dir(batch_dir) if col.startswith("H_")]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _helper_source_paths(helpers: Sequence[str]) -> list[Path]:
    root = _project_root()
    paths = {
        root / "scripts/target_models/helpers/base.py",
        root / "scripts/target_models/helpers/ensemble.py",
        root / "scripts/feature_engineering/htf_helper_cache.py",
        root / "scripts/feature_engineering/htf_feature_acceptance.py",
    }
    for helper in sorted(set(helpers)):
        for rel_path in HELPER_SOURCE_FILE_MAP.get(helper, ()):
            paths.add(root / rel_path)
    return [path for path in sorted(paths) if path.exists()]


def fingerprint_source_files(paths: Sequence[Path]) -> dict[str, Any]:
    digest = hashlib.sha256()
    entries: list[dict[str, Any]] = []
    root = _project_root()
    for path in sorted({Path(p) for p in paths}, key=lambda p: str(p)):
        if not path.exists():
            continue
        payload = path.read_bytes()
        rel_path = str(path.relative_to(root)) if root in path.parents else str(path)
        file_digest = hashlib.sha256(payload).hexdigest()
        digest.update(f"{rel_path}|{file_digest}|{len(payload)}".encode("utf-8"))
        entries.append(
            {
                "path": rel_path,
                "size_bytes": int(len(payload)),
                "sha256": file_digest,
            }
        )
    return {
        "count": int(len(entries)),
        "total_size_bytes": int(sum(item["size_bytes"] for item in entries)),
        "digest": digest.hexdigest(),
        "paths": [item["path"] for item in entries],
    }


def get_helper_contract_metadata(helpers: Sequence[str]) -> dict[str, Any]:
    resolved_helpers = sorted(set(str(name) for name in helpers))
    return {
        "helper_contract_version": HELPER_CONTRACT_VERSION,
        "helper_runtime_contracts": {
            name: HELPER_RUNTIME_CONTRACTS[name]
            for name in resolved_helpers
            if name in HELPER_RUNTIME_CONTRACTS
        },
        "helper_implementation_fingerprint": fingerprint_source_files(
            _helper_source_paths(resolved_helpers)
        ),
    }


def prepare_raw_features_for_helpers(df: pl.DataFrame) -> tuple[np.ndarray, list[str]]:
    close = df["close"].to_numpy().astype(np.float64)
    returns = np.zeros_like(close)
    returns[1:] = np.diff(np.log(np.maximum(close, 1e-10)))
    volatility = pd.Series(returns).rolling(20, min_periods=1).std().fillna(0.01).values

    feature_cols = ["raw_returns", "raw_volatility", "close"]
    features = np.column_stack([returns, volatility, close])

    for col in ["open", "high", "low", "volume"]:
        if col in df.columns:
            vals = df[col].to_numpy().astype(np.float64)
            features = np.column_stack([features, vals])
            feature_cols.append(col)

    return features, feature_cols


def _transform_helper_ensemble_chunk(
    ensemble,
    x_pred: pd.DataFrame,
    x_context: pd.DataFrame,
) -> pd.DataFrame:
    """Transform one helper chunk with helper-specific continuity policy.

    Most helpers still use context-prepended chunk transforms to stabilize
    chunk-start rows. Kalman and EGARCH are now true streaming-state helpers,
    so they must start from the fitted train-end state and consume only the
    real prediction chunk. Replaying prepended context rows would double-count
    already-seen history after the train prefix.
    """

    target_rows = len(x_pred)
    frames: list[pd.DataFrame] = []
    stateful_handoff_helpers = {"kalman", "egarch"}
    for name, helper in ensemble._helpers.items():
        helper_input = x_pred if name in stateful_handoff_helpers else x_context
        output = helper.transform(helper_input)
        helper_df = output.features.reset_index(drop=True)
        if len(helper_df) != target_rows:
            helper_df = helper_df.tail(target_rows).reset_index(drop=True)
        if len(helper_df) != target_rows:
            raise RuntimeError(
                f"Helper '{name}' returned {len(helper_df)} rows for target_rows={target_rows}"
            )
        frames.append(helper_df)

    if not frames:
        return pd.DataFrame(index=np.arange(target_rows))
    return pd.concat(frames, axis=1)


def compute_helpers_walk_forward_raw(
    raw_df: pl.DataFrame,
    target: str,
    horizon: int = 1,
    warmup_rows: int = 5000,
    refit_every: int = 1000,
    helpers: Sequence[str] | None = None,
    start_row: int | None = None,
    verbose: bool = False,
    log: LogFn | None = None,
    chunk_progress_every: int = 20,
) -> pd.DataFrame:
    helper_chunks = list(
        iter_helper_chunk_outputs(
            raw_df=raw_df,
            target=target,
            horizon=horizon,
            warmup_rows=warmup_rows,
            refit_every=refit_every,
            helpers=helpers,
            start_row=start_row,
            verbose=verbose,
            log=log,
            chunk_progress_every=chunk_progress_every,
        )
    )
    if not helper_chunks:
        return pd.DataFrame({"row_idx": []})

    helper_output_list: list[pd.DataFrame] = []
    total_rows = 0
    helper_feature_count = 0
    for pred_start, chunk_df in helper_chunks:
        if chunk_df.empty:
            continue
        helper_feature_count = max(helper_feature_count, len(chunk_df.columns))
        total_rows += len(chunk_df)
        chunk_df = chunk_df.copy()
        chunk_df.insert(0, "row_idx", np.arange(pred_start, pred_start + len(chunk_df), dtype=np.int64))
        helper_output_list.append(chunk_df)

    if not helper_output_list:
        return pd.DataFrame({"row_idx": []})

    helper_df_partial = pd.concat(helper_output_list, axis=0, ignore_index=True)
    if verbose:
        log(
            f"  Generated {helper_feature_count} helper features "
            f"for {total_rows:,} rows"
        )
    return helper_df_partial


def iter_helper_chunk_outputs(
    *,
    raw_df: pl.DataFrame,
    target: str,
    horizon: int = 1,
    warmup_rows: int = 5000,
    refit_every: int = 1000,
    helpers: Sequence[str] | None = None,
    start_row: int | None = None,
    verbose: bool = False,
    log: LogFn | None = None,
    chunk_progress_every: int = 20,
):
    from scripts.target_models.helpers import ensemble as helper_ensemble_module

    create_helper_ensemble = helper_ensemble_module.create_helper_ensemble
    if log is None:
        log = print

    resolved_helpers = list(helpers or DEFAULT_HELPER_NAMES)
    if "kalman" in resolved_helpers and getattr(helper_ensemble_module, "create_kalman_helper", None) is None:
        resolved_helpers.remove("kalman")
        if verbose:
            log("  Helper stage: skipping 'kalman' because filterpy is not installed")

    X, feature_cols = prepare_raw_features_for_helpers(raw_df)
    n_rows = len(X)

    if verbose:
        log(f"  Raw data prepared: {n_rows:,} rows, {len(feature_cols)} columns")
        log(f"  Returns range: {np.nanmin(X[:, 0]):.6f} to {np.nanmax(X[:, 0]):.6f}")
        log(f"  Close range: {np.nanmin(X[:, 2]):.2f} to {np.nanmax(X[:, 2]):.2f}")
        log(f"  Walk-forward: warmup={warmup_rows}, refit_every={refit_every}")

    X_df = pd.DataFrame(X, columns=feature_cols)
    if start_row is None:
        start_row = warmup_rows
    start_row = int(max(start_row, warmup_rows))
    if start_row >= n_rows:
        return pd.DataFrame({"row_idx": []})

    t0 = time.time()
    first_chunk_start = warmup_rows + ((start_row - warmup_rows) // refit_every) * refit_every
    total_chunks = max(0, len(range(first_chunk_start, n_rows, refit_every)))
    processed_chunks = 0

    if verbose:
        total_rows_to_compute = n_rows - start_row
        log(
            f"  Incremental helper compute window: start_row={start_row:,}, "
            f"rows_to_compute={total_rows_to_compute:,}, first_chunk={first_chunk_start:,}"
        )

    for chunk_start in range(first_chunk_start, n_rows, refit_every):
        chunk_end = min(chunk_start + refit_every, n_rows)
        X_train = X_df.iloc[:chunk_start]

        ensemble = create_helper_ensemble(
            target=target,
            horizon=horizon,
            random_state=42 + chunk_start,
            helpers=resolved_helpers,
            enable_boosting=False,
        )
        ensemble.fit(X_train)

        pred_start = max(chunk_start, start_row)
        if pred_start >= chunk_end:
            processed_chunks += 1
            continue

        transform_start = max(0, pred_start - HELPER_TRANSFORM_CONTEXT_ROWS)
        x_pred = X_df.iloc[pred_start:chunk_end]
        x_context = X_df.iloc[transform_start:chunk_end]
        chunk_df = _transform_helper_ensemble_chunk(ensemble, x_pred=x_pred, x_context=x_context).copy()
        processed_chunks += 1

        if verbose and (
            processed_chunks == 1
            or processed_chunks == total_chunks
            or processed_chunks % max(1, chunk_progress_every) == 0
        ):
            progress = processed_chunks / max(total_chunks, 1)
            elapsed = time.time() - t0
            eta = (elapsed / progress) * (1.0 - progress) if progress > 0 else 0.0
            log(
                f"    helper chunk {processed_chunks}/{total_chunks}: "
                f"train_end={chunk_start:,}, predict_rows={max(0, chunk_end - pred_start):,}, "
                f"{progress * 100:.1f}% complete, {elapsed / 60:.1f}m elapsed, "
                f"~{eta / 60:.1f}m remaining"
            )

        yield pred_start, chunk_df.reset_index(drop=True)

    if verbose and processed_chunks > 0:
        elapsed = time.time() - t0
        log(f"  Helper chunk generation finished in {elapsed:.1f}s")


def _meta_rebuild_reasons(
    *,
    meta_path: Path,
    artifact_version: str,
    expected_fields: dict[str, Any],
    source_fingerprint: dict[str, Any],
    schema_columns: list[str] | None = None,
) -> list[str]:
    meta = load_json_safe(meta_path)
    if meta is None:
        return ["missing_meta"]

    reasons: list[str] = []
    if meta.get("artifact_version") != artifact_version:
        reasons.append("artifact_version")
    for key, value in expected_fields.items():
        if meta.get(key) != value:
            reasons.append(key)
    if meta.get("source_fingerprint") != source_fingerprint:
        reasons.append("source_fingerprint")
    if schema_columns is not None and sorted(meta.get("schema_columns", [])) != sorted(schema_columns):
        reasons.append("schema_columns")
    return reasons


def _clear_batch_dir(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for batch_file in directory.glob("batch_*.parquet"):
        batch_file.unlink()


def _collect_batch_ranges(batch_dir: Path) -> dict[int, tuple[pd.Timestamp, pd.Timestamp]]:
    ranges: dict[int, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for batch_id, batch_path in batch_file_map(batch_dir).items():
        stats = (
            pl.scan_parquet(str(batch_path))
            .select(
                [
                    pl.col("timestamp").min().alias("min_ts"),
                    pl.col("timestamp").max().alias("max_ts"),
                ]
            )
            .collect()
        )
        if len(stats) == 0:
            continue
        ranges[batch_id] = (
            pd.Timestamp(stats["min_ts"][0]),
            pd.Timestamp(stats["max_ts"][0]),
        )
    return ranges


def overlapping_cache_batch_ids(
    opt_batch: pl.DataFrame,
    cache_ranges: dict[int, tuple[pd.Timestamp, pd.Timestamp]],
) -> list[int]:
    if len(opt_batch) == 0:
        return []
    min_ts = pd.Timestamp(opt_batch["timestamp"].min())
    max_ts = pd.Timestamp(opt_batch["timestamp"].max())
    overlaps = [
        batch_id
        for batch_id, (cache_min, cache_max) in cache_ranges.items()
        if cache_max >= min_ts and cache_min <= max_ts
    ]
    return sorted(overlaps)


def load_helper_source_batches(
    helper_dir: Path,
    source_batch_ids: Sequence[int],
    helper_cols: Sequence[str],
) -> pl.DataFrame | None:
    parts: list[pl.DataFrame] = []
    for source_batch_id in sorted({int(batch_id) for batch_id in source_batch_ids}):
        batch_path = helper_dir / f"batch_{source_batch_id:04d}.parquet"
        if not batch_path.exists():
            return None
        parts.append(pl.read_parquet(batch_path, columns=["timestamp", *helper_cols]))
    if not parts:
        return None
    return (
        pl.concat(parts, how="diagonal_relaxed")
        .sort("timestamp")
        .unique(subset=["timestamp"], keep="last")
    )


def build_helper_cache_exact(
    *,
    raw_dir: Path,
    cache_dir: Path,
    meta_path: Path | None = None,
    timeframe: str,
    target: str,
    helpers: Sequence[str],
    warmup_rows: int,
    refit_every: int,
    overlap_batches: int,
    rebuild_existing: bool,
    incremental_update: bool,
    artifact_version: str,
    source_fingerprint: dict[str, Any] | None = None,
    chunk_progress_every: int = 20,
    batch_progress_every: int = 500,
    verbose: bool = False,
    log: LogFn | None = None,
) -> HelperCacheBuildResult:
    if log is None:
        log = print
    cache_dir.mkdir(parents=True, exist_ok=True)
    if meta_path is None:
        meta_path = cache_dir / "_helper_cache_meta.json"

    raw_by_id = batch_file_map(raw_dir)
    if not raw_by_id:
        return HelperCacheBuildResult(
            cache_dir=cache_dir,
            meta_path=meta_path,
            run_mode="missing_inputs",
            rows=0,
            helper_cols=0,
            saved_batches=0,
            skipped_batches=0,
            affected_batches_count=0,
            write_batches_count=0,
            first_affected_batch=None,
            write_start_batch=None,
            start_row=None,
            status="missing_inputs",
        )

    cache_by_id = batch_file_map(cache_dir)
    raw_mtime = {batch_id: int(path.stat().st_mtime_ns) for batch_id, path in raw_by_id.items()}
    cache_mtime = {batch_id: int(path.stat().st_mtime_ns) for batch_id, path in cache_by_id.items()}

    helper_contract = get_helper_contract_metadata(helpers)
    source_fingerprint = source_fingerprint or {"raw_batches": fingerprint_batch_dir(raw_dir)}
    source_fingerprint = {
        **source_fingerprint,
        "helper_implementation": helper_contract["helper_implementation_fingerprint"],
    }
    cache_schema_columns = schema_columns_for_batch_dir(cache_dir)
    if not cache_schema_columns:
        cache_schema_columns = (load_json_safe(meta_path) or {}).get("schema_columns", [])
    rebuild_reasons = _meta_rebuild_reasons(
        meta_path=meta_path,
        artifact_version=artifact_version,
        expected_fields={
            "timeframe": timeframe,
            "target": target,
            "helper_names": list(helpers),
            "warmup": int(warmup_rows),
            "refit_every": int(refit_every),
            "helper_contract_version": helper_contract["helper_contract_version"],
            "helper_runtime_contracts": helper_contract["helper_runtime_contracts"],
        },
        source_fingerprint=source_fingerprint,
        schema_columns=cache_schema_columns,
    )

    def _reason_key(reason: str) -> str:
        return reason

    full_rebuild_reasons = {
        "missing_meta",
        "artifact_version",
        "timeframe",
        "target",
        "helper_names",
        "schema_columns",
        "helper_contract_version",
        "helper_runtime_contracts",
    }
    should_full_rebuild = rebuild_existing or any(_reason_key(reason) in full_rebuild_reasons for reason in rebuild_reasons)
    if should_full_rebuild:
        _clear_batch_dir(cache_dir)
        cache_by_id = {}
        cache_mtime = {}

    common_batch_ids = sorted(raw_by_id)
    affected_batch_ids: list[int] = []
    if should_full_rebuild:
        affected_batch_ids = list(common_batch_ids)
        run_mode = "full_recompute"
    else:
        for batch_id in common_batch_ids:
            cache_stamp = cache_mtime.get(batch_id)
            if cache_stamp is None or cache_stamp < raw_mtime[batch_id]:
                affected_batch_ids.append(batch_id)
        run_mode = "incremental_tail"

    if incremental_update and not affected_batch_ids and not rebuild_reasons and not rebuild_existing:
        return HelperCacheBuildResult(
            cache_dir=cache_dir,
            meta_path=meta_path,
            run_mode="current",
            rows=0,
            helper_cols=int(len(helper_cols_from_batch_dir(cache_dir))),
            saved_batches=0,
            skipped_batches=0,
            affected_batches_count=0,
            write_batches_count=0,
            first_affected_batch=None,
            write_start_batch=None,
            start_row=None,
            status="current",
        )

    if not affected_batch_ids:
        affected_batch_ids = [common_batch_ids[-1]]

    first_affected_batch = min(affected_batch_ids)
    write_start_batch = max(common_batch_ids[0], first_affected_batch - int(overlap_batches))
    batches_to_write = [batch_id for batch_id in common_batch_ids if batch_id >= write_start_batch]

    log(
        f"  Helper cache update: affected={len(affected_batch_ids)} "
        f"(first={first_affected_batch}), write_start={write_start_batch}, "
        f"write_batches={len(batches_to_write)}"
    )

    # Helpers only need the raw OHLCV stream plus batch metadata. Reading the
    # full optimized HTF feature matrix here was the main memory blow-up path
    # identified in the 2026-04-13 helper-cache OOM investigation note.
    raw_combined = (
        pl.scan_parquet(
            str(raw_dir / "batch_*.parquet"),
            extra_columns="ignore",
            missing_columns="insert",
        )
        .select(list(HELPER_RAW_SOURCE_COLUMNS))
        .sort("timestamp")
        .collect()
    )
    batch_np = raw_combined["batch_id"].to_numpy()
    batch_change_points = np.flatnonzero(batch_np[1:] != batch_np[:-1]) + 1 if len(batch_np) > 1 else np.array([], dtype=np.int64)
    batch_start_positions = np.concatenate(([0], batch_change_points))
    batch_end_positions = np.concatenate((batch_change_points, [len(batch_np)]))
    batch_offsets = {
        int(batch_np[start]): (int(start), int(end - start))
        for start, end in zip(batch_start_positions, batch_end_positions)
    }
    start_candidates = np.where(batch_np >= write_start_batch)[0]
    if len(start_candidates) == 0:
        return HelperCacheBuildResult(
            cache_dir=cache_dir,
            meta_path=meta_path,
            run_mode="batch_not_in_raw_features",
            rows=0,
            helper_cols=0,
            saved_batches=0,
            skipped_batches=0,
            affected_batches_count=int(len(affected_batch_ids)),
            write_batches_count=int(len(batches_to_write)),
            first_affected_batch=int(first_affected_batch),
            write_start_batch=int(write_start_batch),
            start_row=None,
            status="batch_not_in_raw_features",
        )

    start_row = int(start_candidates[0])
    rows_joined = 0
    saved_batches = 0
    skipped_batches = 0
    helper_cols: list[str] = []
    total_helper_rows = 0
    total_helper_feature_cols = 0
    affected_batch_set = set(affected_batch_ids)
    processed_batch_count = 0
    next_batch_pos = 0
    current_batch_id: int | None = None
    current_batch_parts: list[pl.DataFrame] = []
    helper_chunks_seen = 0

    def _write_cache_batch(batch_id: int, cache_batch: pl.DataFrame) -> None:
        nonlocal rows_joined
        nonlocal saved_batches
        nonlocal skipped_batches
        nonlocal processed_batch_count
        nonlocal next_batch_pos
        if next_batch_pos >= len(batches_to_write) or batch_id != batches_to_write[next_batch_pos]:
            raise RuntimeError(
                f"Helper cache batch order mismatch: batch_id={batch_id} "
                f"expected={batches_to_write[next_batch_pos] if next_batch_pos < len(batches_to_write) else 'end'}"
            )

        batch_path = cache_dir / f"batch_{batch_id:04d}.parquet"
        force_rewrite = batch_id in affected_batch_set

        if batch_path.exists() and not force_rewrite:
            existing = pl.read_parquet(batch_path, columns=["timestamp"])
            same_rows = len(existing) == len(cache_batch)
            same_last_ts = existing["timestamp"].max() == cache_batch["timestamp"].max()
            if same_rows and same_last_ts:
                skipped_batches += 1
                rows_joined += len(cache_batch)
                processed_batch_count += 1
                next_batch_pos += 1
                if processed_batch_count % max(1, batch_progress_every) == 0:
                    log(f"    cache batches processed {processed_batch_count}/{len(batches_to_write)}")
                return

        cache_batch.write_parquet(batch_path, compression="zstd")
        saved_batches += 1
        rows_joined += len(cache_batch)
        processed_batch_count += 1
        next_batch_pos += 1
        if processed_batch_count % max(1, batch_progress_every) == 0:
            log(f"    cache batches processed {processed_batch_count}/{len(batches_to_write)}")

    def _null_cache_batch(
        batch_id: int,
        *,
        batch_offsets_by_id: dict[int, tuple[int, int]],
        raw_batch_rows: pl.DataFrame,
    ) -> pl.DataFrame:
        batch_start, batch_len = batch_offsets_by_id[batch_id]
        ts_only = raw_batch_rows.slice(batch_start, batch_len).select(["timestamp"])
        null_columns = [
            pl.lit(None, dtype=pl.Float64).alias(col)
            for col in helper_cols
        ]
        return ts_only.with_columns(null_columns).select(["timestamp", *helper_cols])

    def _flush_current_batch() -> None:
        nonlocal current_batch_id
        nonlocal current_batch_parts
        if current_batch_id is None or not current_batch_parts:
            return

        if len(current_batch_parts) == 1:
            cache_batch = current_batch_parts[0]
        else:
            cache_batch = pl.concat(current_batch_parts, how="vertical_relaxed")
        cache_batch = cache_batch.select(["timestamp", *helper_cols])
        _write_cache_batch(current_batch_id, cache_batch)
        current_batch_id = None
        current_batch_parts = []

    for pred_start, chunk_df in iter_helper_chunk_outputs(
        raw_df=raw_combined,
        target=target.replace("target_", ""),
        horizon=1,
        warmup_rows=warmup_rows,
        refit_every=refit_every,
        helpers=helpers,
        start_row=start_row,
        verbose=verbose,
        log=log,
        chunk_progress_every=chunk_progress_every,
    ):
        if chunk_df.empty:
            continue

        helper_chunks_seen += 1
        total_helper_rows += len(chunk_df)
        total_helper_feature_cols = max(total_helper_feature_cols, len(chunk_df.columns))
        if not helper_cols:
            helper_cols = [col for col in chunk_df.columns if col.startswith("H_")]

        batch_chunk = batch_np[pred_start : pred_start + len(chunk_df)]
        if len(batch_chunk) != len(chunk_df):
            raise RuntimeError(
                f"Helper chunk row mismatch: batch_chunk={len(batch_chunk)} chunk_df={len(chunk_df)}"
            )

        change_points = np.flatnonzero(batch_chunk[1:] != batch_chunk[:-1]) + 1
        segment_bounds = np.concatenate(([0], change_points, [len(chunk_df)]))
        chunk_pl = pl.from_pandas(chunk_df)

        for seg_start, seg_end in zip(segment_bounds[:-1], segment_bounds[1:]):
            batch_id = int(batch_chunk[seg_start])
            if current_batch_id is not None and batch_id != current_batch_id:
                _flush_current_batch()
            while next_batch_pos < len(batches_to_write) and batches_to_write[next_batch_pos] < batch_id:
                _write_cache_batch(
                    batches_to_write[next_batch_pos],
                    _null_cache_batch(
                        batches_to_write[next_batch_pos],
                        batch_offsets_by_id=batch_offsets,
                        raw_batch_rows=raw_combined,
                    ),
                )
            if current_batch_id is None:
                batch_start, _batch_len = batch_offsets[batch_id]
                segment_global_start = int(pred_start + seg_start)
                if segment_global_start > batch_start:
                    current_batch_parts.append(
                        _null_cache_batch(
                            batch_id,
                            batch_offsets_by_id=batch_offsets,
                            raw_batch_rows=raw_combined,
                        ).slice(0, segment_global_start - batch_start)
                    )
            current_batch_id = batch_id
            helper_slice = chunk_pl.slice(int(seg_start), int(seg_end - seg_start))
            ts_slice = raw_combined.slice(int(pred_start + seg_start), int(seg_end - seg_start)).select(
                ["timestamp"]
            )
            current_batch_parts.append(ts_slice.hstack(helper_slice))

    _flush_current_batch()
    while helper_cols and next_batch_pos < len(batches_to_write):
        _write_cache_batch(
            batches_to_write[next_batch_pos],
            _null_cache_batch(
                batches_to_write[next_batch_pos],
                batch_offsets_by_id=batch_offsets,
                raw_batch_rows=raw_combined,
            ),
        )

    if helper_chunks_seen == 0 or not helper_cols:
        return HelperCacheBuildResult(
            cache_dir=cache_dir,
            meta_path=meta_path,
            run_mode=run_mode,
            rows=0,
            helper_cols=0,
            saved_batches=0,
            skipped_batches=0,
            affected_batches_count=int(len(affected_batch_ids)),
            write_batches_count=int(len(batches_to_write)),
            first_affected_batch=int(first_affected_batch),
            write_start_batch=int(write_start_batch),
            start_row=int(start_row),
            status="empty_helper_output",
        )

    if verbose:
        log(
            f"  Generated {total_helper_feature_cols} helper features "
            f"for {total_helper_rows:,} rows"
        )

    if processed_batch_count != len(batches_to_write):
        raise RuntimeError(
            "Helper cache streaming write count mismatch: "
            f"processed={processed_batch_count} expected={len(batches_to_write)}"
        )

    del raw_combined
    del batch_np
    del batch_offsets
    gc.collect()

    write_json(
        meta_path,
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "artifact_version": artifact_version,
            "timeframe": timeframe,
            "target": target,
            "helper_names": list(helpers),
            "helper_contract_version": helper_contract["helper_contract_version"],
            "helper_runtime_contracts": helper_contract["helper_runtime_contracts"],
            "helper_implementation_fingerprint": helper_contract["helper_implementation_fingerprint"],
            "warmup": int(warmup_rows),
            "refit_every": int(refit_every),
            "source_fingerprint": source_fingerprint,
            "schema_columns": schema_columns_for_batch_dir(cache_dir),
            "run_mode": run_mode,
            "rebuild_reasons": rebuild_reasons,
            "helper_cache_dir": str(cache_dir),
            "first_affected_batch": int(first_affected_batch),
            "write_start_batch": int(write_start_batch),
            "affected_batches_count": int(len(affected_batch_ids)),
            "write_batches_count": int(len(batches_to_write)),
            "start_row": int(start_row),
            "rows": int(rows_joined),
            "helper_cols": int(len(helper_cols)),
            "saved_batches": int(saved_batches),
            "skipped_batches": int(skipped_batches),
        },
    )

    return HelperCacheBuildResult(
        cache_dir=cache_dir,
        meta_path=meta_path,
        run_mode=run_mode,
        rows=int(rows_joined),
        helper_cols=int(len(helper_cols)),
        saved_batches=int(saved_batches),
        skipped_batches=int(skipped_batches),
        affected_batches_count=int(len(affected_batch_ids)),
        write_batches_count=int(len(batches_to_write)),
        first_affected_batch=int(first_affected_batch),
        write_start_batch=int(write_start_batch),
        start_row=int(start_row),
        status="created",
    )


def materialize_helpers_from_cache(
    *,
    cache_dir: Path,
    optimized_dir: Path,
    output_dir: Path,
    meta_path: Path | None = None,
    family: str,
    timeframe: str,
    target: str,
    overlap_batches: int,
    rebuild_existing: bool,
    incremental_skip_unchanged: bool,
    artifact_version: str,
    source_fingerprint: dict[str, Any],
    extra_meta: dict[str, Any] | None = None,
    helper_contract_version: str | None = None,
    helper_runtime_contracts: dict[str, str] | None = None,
    write_combined: bool = False,
    batch_progress_every: int = 500,
    log: LogFn | None = None,
) -> HelperMaterializationResult:
    if log is None:
        log = print
    output_dir.mkdir(parents=True, exist_ok=True)
    if meta_path is None:
        meta_path = output_dir / "_helpers_meta.json"

    raw_cache_cols = helper_cols_from_batch_dir(cache_dir)
    if not raw_cache_cols:
        return HelperMaterializationResult(
            output_dir=output_dir,
            meta_path=meta_path,
            run_mode="missing_cache",
            rows=0,
            helper_cols=0,
            saved_batches=0,
            skipped_batches=0,
            affected_batches_count=0,
            write_batches_count=0,
            first_affected_batch=None,
            write_start_batch=None,
            status="missing_cache",
        )
    excluded_cache_cols = get_final_output_excluded_columns(raw_cache_cols, stage="helpers")
    cache_cols = [col for col in raw_cache_cols if col not in set(excluded_cache_cols)]
    if not cache_cols:
        return HelperMaterializationResult(
            output_dir=output_dir,
            meta_path=meta_path,
            run_mode="all_helper_cols_excluded",
            rows=0,
            helper_cols=0,
            saved_batches=0,
            skipped_batches=0,
            affected_batches_count=0,
            write_batches_count=0,
            first_affected_batch=None,
            write_start_batch=None,
            status="all_helper_cols_excluded",
        )

    opt_by_id = batch_file_map(optimized_dir)
    if not opt_by_id:
        return HelperMaterializationResult(
            output_dir=output_dir,
            meta_path=meta_path,
            run_mode="missing_optimized",
            rows=0,
            helper_cols=int(len(cache_cols)),
            saved_batches=0,
            skipped_batches=0,
            affected_batches_count=0,
            write_batches_count=0,
            first_affected_batch=None,
            write_start_batch=None,
            status="missing_optimized",
        )

    output_by_id = batch_file_map(output_dir)
    output_mtime = {batch_id: int(path.stat().st_mtime_ns) for batch_id, path in output_by_id.items()}
    opt_mtime = {batch_id: int(path.stat().st_mtime_ns) for batch_id, path in opt_by_id.items()}
    cache_mtime = {batch_id: int(path.stat().st_mtime_ns) for batch_id, path in batch_file_map(cache_dir).items()}
    output_schema_columns = schema_columns_for_batch_dir(output_dir)
    if not output_schema_columns:
        output_schema_columns = (load_json_safe(meta_path) or {}).get("schema_columns", [])
    rebuild_reasons = _meta_rebuild_reasons(
        meta_path=meta_path,
        artifact_version=artifact_version,
        expected_fields={
            "family": family,
            "timeframe": timeframe,
            "target": target,
            "helper_policy_version": FINAL_OUTPUT_FEATURE_POLICY_VERSION,
            **(
                {"helper_contract_version": helper_contract_version}
                if helper_contract_version is not None
                else {}
            ),
            **(
                {"helper_runtime_contracts": helper_runtime_contracts}
                if helper_runtime_contracts is not None
                else {}
            ),
        },
        source_fingerprint=source_fingerprint,
        schema_columns=output_schema_columns,
    )
    full_rebuild_reasons = {
        "missing_meta",
        "artifact_version",
        "family",
        "timeframe",
        "target",
        "schema_columns",
        "helper_policy_version",
        "helper_contract_version",
        "helper_runtime_contracts",
    }
    should_full_rebuild = rebuild_existing or any(reason in full_rebuild_reasons for reason in rebuild_reasons)
    if should_full_rebuild:
        _clear_batch_dir(output_dir)
        output_by_id = {}
        output_mtime = {}

    cache_ranges = _collect_batch_ranges(cache_dir)
    if excluded_cache_cols:
        log(
            f"  Helper output policy: excluding {len(excluded_cache_cols)} helper columns "
            f"from model-facing outputs"
        )
    common_batch_ids = sorted(opt_by_id)
    affected_batch_ids: list[int] = []
    run_mode = "full_recompute" if should_full_rebuild else "incremental_tail"
    for batch_id in common_batch_ids:
        opt_batch = pl.read_parquet(opt_by_id[batch_id], columns=["timestamp"])
        source_cache_batch_ids = overlapping_cache_batch_ids(opt_batch, cache_ranges)
        if not source_cache_batch_ids:
            raise ValueError(
                f"no overlapping helper cache batches for {family}/{timeframe}/{target} batch {batch_id}"
            )
        cache_stamp = max(cache_mtime.get(source_batch_id, 0) for source_batch_id in source_cache_batch_ids)
        output_stamp = output_mtime.get(batch_id)
        if should_full_rebuild or output_stamp is None or output_stamp < max(opt_mtime[batch_id], cache_stamp):
            affected_batch_ids.append(batch_id)

    if incremental_skip_unchanged and not affected_batch_ids and not rebuild_reasons and not rebuild_existing:
        return HelperMaterializationResult(
            output_dir=output_dir,
            meta_path=meta_path,
            run_mode="current",
            rows=0,
            helper_cols=int(len(cache_cols)),
            saved_batches=0,
            skipped_batches=0,
            affected_batches_count=0,
            write_batches_count=0,
            first_affected_batch=None,
            write_start_batch=None,
            status="current",
        )

    if not affected_batch_ids:
        affected_batch_ids = [common_batch_ids[-1]]

    first_affected_batch = min(affected_batch_ids)
    write_start_batch = max(common_batch_ids[0], first_affected_batch - int(overlap_batches))
    batches_to_write = [batch_id for batch_id in common_batch_ids if batch_id >= write_start_batch]
    affected_batch_set = set(affected_batch_ids)
    log(
        f"  Helper materialization update: affected={len(affected_batch_ids)} "
        f"(first={first_affected_batch}), write_start={write_start_batch}, "
        f"write_batches={len(batches_to_write)}"
    )

    rows_joined = 0
    saved_batches = 0
    skipped_batches = 0
    for index, batch_id in enumerate(batches_to_write, 1):
        opt_batch = pl.read_parquet(opt_by_id[batch_id]).with_columns(pl.lit(batch_id).alias("batch_id"))
        source_cache_batch_ids = overlapping_cache_batch_ids(opt_batch.select(["timestamp"]), cache_ranges)
        helper_source = load_helper_source_batches(cache_dir, source_cache_batch_ids, cache_cols)
        if helper_source is None:
            raise ValueError(
                f"missing helper cache batch for {family}/{timeframe}/{target} batch {batch_id} "
                f"(sources={source_cache_batch_ids})"
            )

        missing_helper_ts = int(
            opt_batch.join(helper_source.select(["timestamp"]), on="timestamp", how="anti")
            .select(pl.len())
            .item()
        )
        if missing_helper_ts > 0:
            raise ValueError(
                f"helper cache missing {missing_helper_ts} timestamps for {family}/{timeframe}/{target} "
                f"batch {batch_id}"
            )

        enriched_batch = opt_batch.join(helper_source, on="timestamp", how="left")
        batch_path = output_dir / f"batch_{batch_id:04d}.parquet"
        force_rewrite = batch_id in affected_batch_set
        if batch_path.exists() and not force_rewrite:
            existing = pl.read_parquet(batch_path, columns=["timestamp"])
            same_rows = len(existing) == len(enriched_batch)
            same_last_ts = existing["timestamp"].max() == enriched_batch["timestamp"].max()
            if same_rows and same_last_ts:
                skipped_batches += 1
                rows_joined += len(enriched_batch)
                if index % max(1, batch_progress_every) == 0:
                    log(f"    helper batches processed {index}/{len(batches_to_write)}")
                continue

        enriched_batch.write_parquet(batch_path, compression="zstd")
        saved_batches += 1
        rows_joined += len(enriched_batch)
        if index % max(1, batch_progress_every) == 0:
            log(f"    helper batches processed {index}/{len(batches_to_write)}")

    if write_combined:
        pl.concat(
            [pl.read_parquet(batch_file) for batch_file in sorted(output_dir.glob("batch_*.parquet"))]
        ).sort("timestamp").write_parquet(output_dir / "combined.parquet")

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_version": artifact_version,
        "family": family,
        "timeframe": timeframe,
        "target": target,
        "helper_policy_version": FINAL_OUTPUT_FEATURE_POLICY_VERSION,
        "helper_contract_version": helper_contract_version,
        "helper_runtime_contracts": helper_runtime_contracts,
        "source_fingerprint": source_fingerprint,
        "schema_columns": schema_columns_for_batch_dir(output_dir),
        "run_mode": run_mode,
        "rebuild_reasons": rebuild_reasons,
        "helper_cache_dir": str(cache_dir),
        "first_affected_batch": int(first_affected_batch),
        "write_start_batch": int(write_start_batch),
        "affected_batches_count": int(len(affected_batch_ids)),
        "write_batches_count": int(len(batches_to_write)),
        "rows": int(rows_joined),
        "helper_cols": int(len(cache_cols)),
        "excluded_helper_cols": excluded_cache_cols,
        "saved_batches": int(saved_batches),
        "skipped_batches": int(skipped_batches),
        "write_helpers_combined": bool(write_combined),
    }
    if extra_meta:
        payload.update(extra_meta)
    write_json(meta_path, payload)

    return HelperMaterializationResult(
        output_dir=output_dir,
        meta_path=meta_path,
        run_mode=run_mode,
        rows=int(rows_joined),
        helper_cols=int(len(cache_cols)),
        saved_batches=int(saved_batches),
        skipped_batches=int(skipped_batches),
        affected_batches_count=int(len(affected_batch_ids)),
        write_batches_count=int(len(batches_to_write)),
        first_affected_batch=int(first_affected_batch),
        write_start_batch=int(write_start_batch),
        status="created",
    )
