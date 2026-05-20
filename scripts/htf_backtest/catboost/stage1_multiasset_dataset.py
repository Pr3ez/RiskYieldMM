"""Stage-1-compatible multi-asset HTF dataset assembly.

This module builds a merged feature/label root for one prediction target asset,
one regime/family root, and one selected context-asset set. It deliberately
keeps the downstream CatBoost Stage-1 runner contract unchanged:

``features_dir/1m/target_4class/batch_*.parquet``
``labels_dir/1m/batch_*.parquet``

The target asset remains the row authority. Context assets are joined by exact
timestamp only, so v1 never repeats stale context values across closed sessions
or missing rows.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from TA_backtest_optimization.materialize_ta_flags import (
    parse_ta_timeframes,
    ta_flag_columns,
    ta_flags_path,
)
from scripts.feature_engineering.htf_asset_registry import (
    CORE_HTF_ASSET_IDS,
    normalize_htf_asset_id,
)
from scripts.htf_backtest.catboost.utils import get_feature_columns


TF = "1m"
TARGET_COL = "target_4class"
FEATURE_TARGET_COL = TARGET_COL
MULTIASSET_SOURCE_ROOT = "htf_multiasset"
MULTIASSET_MERGED_ROOT = "htf_multiasset_merged"

# `bar_in_batch_norm` is intentionally kept unprefixed for the target asset.
# Existing Stage-1 loaders use this column name for optional tail filtering, and
# the current feature policy intentionally allows it as a model feature.
TARGET_UNPREFIXED_FEATURE_COLUMNS = ("bar_in_batch_norm",)


@dataclass(frozen=True)
class Stage1RootLayout:
    """Input root contract for one regime/family Stage-1 dataset."""

    root_key: str
    root_id: str
    regime: str
    family: str
    feature_root: str
    label_root: str


STAGE1_MULTIASSET_ROOT_LAYOUTS: dict[str, Stage1RootLayout] = {
    "8h/B": Stage1RootLayout(
        root_key="8h/B",
        root_id="8h_b",
        regime="8h",
        family="B",
        feature_root="htf_with_helpers",
        label_root="htf_4class_labels",
    ),
    "8h/C": Stage1RootLayout(
        root_key="8h/C",
        root_id="8h_c",
        regime="8h",
        family="C",
        feature_root="htf_with_helpers_shift4h",
        label_root="htf_4class_labels_shift4h",
    ),
    "24h/B": Stage1RootLayout(
        root_key="24h/B",
        root_id="24h_b",
        regime="24h",
        family="B",
        feature_root="htf_with_helpers_24h",
        label_root="htf_4class_labels_24h",
    ),
    "24h/C": Stage1RootLayout(
        root_key="24h/C",
        root_id="24h_c",
        regime="24h",
        family="C",
        feature_root="htf_with_helpers_24h_shift12h",
        label_root="htf_4class_labels_24h_shift12h",
    ),
    "7d/B": Stage1RootLayout(
        root_key="7d/B",
        root_id="7d_b",
        regime="7d",
        family="B",
        feature_root="htf_with_helpers_7d",
        label_root="htf_4class_labels_7d",
    ),
    "7d/C": Stage1RootLayout(
        root_key="7d/C",
        root_id="7d_c",
        regime="7d",
        family="C",
        feature_root="htf_with_helpers_7d_shift84h",
        label_root="htf_4class_labels_7d_shift84h",
    ),
}


@dataclass(frozen=True)
class FeatureFileMeta:
    """Timestamp range metadata for one feature batch file."""

    path: Path
    batch_id: int
    row_count: int
    timestamp_min: datetime | None
    timestamp_max: datetime | None


@dataclass(frozen=True)
class AssetFeatureIndex:
    """Schema and timestamp-range index for one asset/root feature directory."""

    asset_id: str
    feature_dir: Path
    files: tuple[FeatureFileMeta, ...]
    model_columns: tuple[str, ...]
    excluded_model_columns: tuple[str, ...]
    duplicate_timestamp_count: int
    input_rows: int

    def overlapping_files(
        self,
        *,
        timestamp_min: datetime,
        timestamp_max: datetime,
    ) -> list[Path]:
        """Return feature files whose timestamp range overlaps a target batch."""
        paths: list[Path] = []
        for meta in self.files:
            if meta.timestamp_min is None or meta.timestamp_max is None:
                continue
            if meta.timestamp_max < timestamp_min or meta.timestamp_min > timestamp_max:
                continue
            paths.append(meta.path)
        return paths


@dataclass(frozen=True)
class MultiAssetAssemblyResult:
    """Resolved Stage-1 directories and manifest for one merged root."""

    target_asset: str
    context_assets: tuple[str, ...]
    context_hash: str
    root_key: str
    root_id: str
    features_dir: Path
    labels_dir: Path
    manifest_path: Path
    run_id: str
    manifest: dict[str, Any]


def parse_stage1_target_assets(raw: str | None) -> tuple[str, ...]:
    """Parse `--target-assets` into supported HTF asset ids.

    `core` expands to the configured core universe. Duplicate entries are
    removed while preserving order.
    """
    selector = "core" if raw is None or not raw.strip() else raw.strip()
    if selector.lower() == "core":
        return CORE_HTF_ASSET_IDS
    if selector.lower() == "core-ex-target":
        raise ValueError("--target-assets cannot use core-ex-target")
    return _dedupe_assets(
        normalize_htf_asset_id(part)
        for part in selector.split(",")
        if part.strip()
    )


def parse_stage1_context_assets(
    raw: str | None,
    *,
    target_asset: str,
) -> tuple[str, ...]:
    """Parse `--context-assets` for one target asset.

    Supported selectors:
    - empty / None: no context assets
    - `core`: all core assets except the target
    - `core-ex-target`: all core assets except the target
    - comma-separated asset ids
    """
    target_asset = normalize_htf_asset_id(target_asset)
    if raw is None or not raw.strip():
        return ()

    selector = raw.strip().lower()
    if selector in {"core", "core-ex-target"}:
        return tuple(asset for asset in CORE_HTF_ASSET_IDS if asset != target_asset)

    assets = _dedupe_assets(
        normalize_htf_asset_id(part)
        for part in raw.split(",")
        if part.strip()
    )
    if target_asset in assets:
        raise ValueError(
            "--context-assets cannot include the target asset; target features are "
            "already included with the T_<asset>__ prefix."
        )
    return assets


def build_context_set_hash(
    *,
    target_asset: str,
    context_assets: tuple[str, ...],
) -> str:
    """Return a stable short identifier for the selected context asset set."""
    target_asset = normalize_htf_asset_id(target_asset)
    normalized_context = tuple(normalize_htf_asset_id(asset) for asset in context_assets)
    core_ex_target = tuple(asset for asset in CORE_HTF_ASSET_IDS if asset != target_asset)
    if not normalized_context:
        return "selfonly"
    if set(normalized_context) == set(core_ex_target):
        return "corexself"
    payload = ",".join(sorted(normalized_context))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def build_multiasset_stage1_run_id(
    *,
    target_asset: str,
    root_key: str,
    context_hash: str,
) -> str:
    """Return the Stage-1 run id for one target/root/context identity."""
    layout = _root_layout(root_key)
    return (
        f"stage1_catboost_{normalize_htf_asset_id(target_asset).lower()}_"
        f"{layout.root_id}_ctx_{context_hash}_live"
    )


def build_multiasset_stage1_dataset(
    *,
    project_root: Path,
    target_asset: str,
    context_assets: tuple[str, ...],
    root_key: str,
    output_base_dir: Path | None = None,
    input_base_dir: Path | None = None,
    target_col: str = TARGET_COL,
    tf: str = TF,
    feature_target_col: str = FEATURE_TARGET_COL,
    clear_existing: bool = True,
    include_ta_flags: bool = False,
    ta_timeframes: tuple[str, ...] = (),
) -> MultiAssetAssemblyResult:
    """Build one merged Stage-1 dataset root from per-asset HTF outputs."""
    project_root = Path(project_root)
    target_asset = normalize_htf_asset_id(target_asset)
    context_assets = tuple(normalize_htf_asset_id(asset) for asset in context_assets)
    ta_timeframes = parse_ta_timeframes(ta_timeframes) if include_ta_flags else ()
    layout = _root_layout(root_key)
    input_base_dir = input_base_dir or project_root / "data" / MULTIASSET_SOURCE_ROOT
    output_base_dir = output_base_dir or project_root / "data" / MULTIASSET_MERGED_ROOT
    context_hash = build_context_set_hash(
        target_asset=target_asset,
        context_assets=context_assets,
    )
    root_output_dir = (
        output_base_dir / target_asset.lower() / context_hash / layout.root_id
    )
    features_dir = root_output_dir / "features"
    labels_dir = root_output_dir / "labels"
    feature_output_dir = features_dir / tf / feature_target_col
    label_output_dir = labels_dir / tf

    if clear_existing:
        _clear_generated_root(root_output_dir)
    feature_output_dir.mkdir(parents=True, exist_ok=True)
    label_output_dir.mkdir(parents=True, exist_ok=True)

    target_feature_dir = _asset_feature_dir(
        input_base_dir,
        asset_id=target_asset,
        layout=layout,
        tf=tf,
        feature_target_col=feature_target_col,
    )
    target_label_dir = _asset_label_dir(
        input_base_dir,
        asset_id=target_asset,
        layout=layout,
        tf=tf,
    )
    target_index = _build_feature_index(
        target_asset,
        feature_dir=target_feature_dir,
        target_col=target_col,
    )
    if target_index.duplicate_timestamp_count:
        raise ValueError(
            f"Target {target_asset} {root_key} has duplicate feature timestamps: "
            f"{target_index.duplicate_timestamp_count}"
        )

    context_indexes = [
        _build_feature_index(
            asset,
            feature_dir=_asset_feature_dir(
                input_base_dir,
                asset_id=asset,
                layout=layout,
                tf=tf,
                feature_target_col=feature_target_col,
            ),
            target_col=target_col,
        )
        for asset in context_assets
    ]
    for index in context_indexes:
        if index.duplicate_timestamp_count:
            raise ValueError(
                f"Context {index.asset_id} {root_key} has duplicate feature "
                f"timestamps: {index.duplicate_timestamp_count}"
            )

    target_label_paths = _batch_files(target_label_dir)
    source_rows_by_context = {
        index.asset_id: int(index.input_rows) for index in context_indexes
    }
    context_excluded_columns = {
        index.asset_id: list(index.excluded_model_columns) for index in context_indexes
    }
    target_excluded_columns = list(target_index.excluded_model_columns)

    target_prefixed_cols = tuple(
        col
        for col in target_index.model_columns
        if col not in TARGET_UNPREFIXED_FEATURE_COLUMNS
    )
    target_unprefixed_cols = tuple(
        col
        for col in TARGET_UNPREFIXED_FEATURE_COLUMNS
        if col in target_index.model_columns
    )
    target_ta_cols = _ta_output_columns(
        project_root=project_root,
        asset_id=target_asset,
        role_prefix=f"T_{target_asset}__",
        ta_timeframes=ta_timeframes,
        require=include_ta_flags,
    )
    context_ta_cols = {
        asset: _ta_output_columns(
            project_root=project_root,
            asset_id=asset,
            role_prefix=f"C_{asset}__",
            ta_timeframes=ta_timeframes,
            require=include_ta_flags,
        )
        for asset in context_assets
    }
    output_feature_columns = [
        *target_unprefixed_cols,
        *(f"T_{target_asset}__{col}" for col in target_prefixed_cols),
        *target_ta_cols,
    ]
    for index in context_indexes:
        output_feature_columns.extend(
            f"C_{index.asset_id}__{col}" for col in index.model_columns
        )
        output_feature_columns.extend(context_ta_cols[index.asset_id])

    batch_summaries: list[dict[str, Any]] = []
    target_feature_rows = 0
    target_label_rows = 0
    output_rows = 0
    skipped_batches = 0
    null_feature_count = 0
    rows_dropped_by_null_features = 0
    timestamp_min: datetime | None = None
    timestamp_max: datetime | None = None

    for target_meta in target_index.files:
        if target_meta.timestamp_min is None or target_meta.timestamp_max is None:
            skipped_batches += 1
            continue

        target_batch = _read_target_feature_batch(
            target_meta.path,
            asset_id=target_asset,
            model_columns=target_index.model_columns,
            target_unprefixed_cols=target_unprefixed_cols,
            target_prefixed_cols=target_prefixed_cols,
        )
        if include_ta_flags:
            target_batch = _join_ta_flags(
                target_batch,
                project_root=project_root,
                asset_id=target_asset,
                role_prefix=f"T_{target_asset}__",
                ta_timeframes=ta_timeframes,
                timestamp_min=target_meta.timestamp_min,
                timestamp_max=target_meta.timestamp_max,
            )
        if _duplicate_count(target_batch, ["timestamp"]):
            raise ValueError(f"Duplicate target timestamps in {target_meta.path}")
        target_feature_rows += len(target_batch)

        merged = target_batch
        for context_index in context_indexes:
            context_batch = _read_context_window(
                context_index,
                timestamp_min=target_meta.timestamp_min,
                timestamp_max=target_meta.timestamp_max,
            )
            if include_ta_flags:
                context_batch = _join_ta_flags(
                    context_batch,
                    project_root=project_root,
                    asset_id=context_index.asset_id,
                    role_prefix=f"C_{context_index.asset_id}__",
                    ta_timeframes=ta_timeframes,
                    timestamp_min=target_meta.timestamp_min,
                    timestamp_max=target_meta.timestamp_max,
                )
            merged = merged.join(context_batch, on="timestamp", how="inner")

        merged = merged.sort(["batch_id", "timestamp"])
        rows_before_null_drop = len(merged)
        merged = _drop_null_feature_rows(merged, output_feature_columns)
        null_dropped_rows = int(rows_before_null_drop - len(merged))
        rows_dropped_by_null_features += null_dropped_rows

        output_duplicate_count = _duplicate_count(merged, ["timestamp", "batch_id"])
        if output_duplicate_count:
            raise ValueError(
                f"Merged output {target_asset} {root_key} batch "
                f"{target_meta.batch_id:04d} has duplicate timestamp,batch_id rows: "
                f"{output_duplicate_count}"
            )

        feature_nulls = _feature_null_count(merged, output_feature_columns)
        if feature_nulls:
            null_cols = _columns_with_nulls(merged, output_feature_columns)
            raise ValueError(
                f"Merged output {target_asset} {root_key} batch "
                f"{target_meta.batch_id:04d} contains null feature values: "
                f"{feature_nulls} nulls in {null_cols[:10]}"
            )
        null_feature_count += feature_nulls

        label_path = target_label_paths.get(target_meta.batch_id)
        if label_path is None:
            raise FileNotFoundError(
                f"Target label batch not found for {target_asset} {root_key}: "
                f"batch_{target_meta.batch_id:04d}.parquet under {target_label_dir}"
            )
        labels_out = _read_target_labels_for_merged_rows(
            label_path,
            merged=merged,
            target_col=target_col,
        )
        target_label_rows += int(
            pl.read_parquet(label_path, columns=["timestamp"]).height
        )

        batch_output_rows = len(merged)
        dropped_rows = int(len(target_batch) - batch_output_rows)
        dropped_rows_missing_context = int(dropped_rows - null_dropped_rows)
        if batch_output_rows == 0:
            skipped_batches += 1
        else:
            out_name = f"batch_{target_meta.batch_id:04d}.parquet"
            merged.select(
                ["timestamp", "batch_id", *output_feature_columns]
            ).write_parquet(feature_output_dir / out_name)
            labels_out.write_parquet(label_output_dir / out_name)
            output_rows += batch_output_rows
            batch_min = merged["timestamp"].min()
            batch_max = merged["timestamp"].max()
            timestamp_min = (
                batch_min
                if timestamp_min is None or batch_min < timestamp_min
                else timestamp_min
            )
            timestamp_max = (
                batch_max
                if timestamp_max is None or batch_max > timestamp_max
                else timestamp_max
            )

        batch_summaries.append(
            {
                "batch_id": int(target_meta.batch_id),
                "target_rows": int(len(target_batch)),
                "output_rows": int(batch_output_rows),
                "dropped_rows_missing_context": int(dropped_rows_missing_context),
                "dropped_rows_null_features": int(null_dropped_rows),
                "feature_path": str(target_meta.path),
                "label_path": str(label_path),
            }
        )

    schema_hash = _schema_hash(["timestamp", "batch_id", *output_feature_columns])
    run_id = build_multiasset_stage1_run_id(
        target_asset=target_asset,
        root_key=root_key,
        context_hash=context_hash,
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_asset": target_asset,
        "context_assets": list(context_assets),
        "context_hash": context_hash,
        "root": root_key,
        "root_id": layout.root_id,
        "regime": layout.regime,
        "family": layout.family,
        "target_col": target_col,
        "timeframe": tf,
        "feature_target_col": feature_target_col,
        "run_id": run_id,
        "source_paths": {
            "target_features": str(target_feature_dir),
            "target_labels": str(target_label_dir),
            "context_features": {
                index.asset_id: str(index.feature_dir) for index in context_indexes
            },
        },
        "output_paths": {
            "features_dir": str(features_dir),
            "labels_dir": str(labels_dir),
            "manifest_path": str(root_output_dir / "manifest.json"),
        },
        "input_rows": {
            "target_features": int(target_feature_rows),
            "target_labels": int(target_label_rows),
            "context_features": source_rows_by_context,
        },
        "output_rows": int(output_rows),
        "rows_dropped_by_missing_context": int(
            target_feature_rows - output_rows - rows_dropped_by_null_features
        ),
        "rows_dropped_by_null_features": int(rows_dropped_by_null_features),
        "skipped_batches": int(skipped_batches),
        "written_batches": int(len(list(feature_output_dir.glob("batch_*.parquet")))),
        "duplicate_count": 0,
        "null_feature_count": int(null_feature_count),
        "schema_hash": schema_hash,
        "feature_columns": output_feature_columns,
        "feature_columns_count": int(len(output_feature_columns)),
        "target_unprefixed_feature_columns": list(target_unprefixed_cols),
        "ta_flags_enabled": bool(include_ta_flags),
        "ta_timeframes": list(ta_timeframes),
        "ta_source_paths": _ta_source_paths(
            project_root=project_root,
            assets=(target_asset, *context_assets),
            ta_timeframes=ta_timeframes,
        )
        if include_ta_flags
        else {},
        "ta_feature_columns_count": int(
            len(target_ta_cols) + sum(len(cols) for cols in context_ta_cols.values())
        ),
        "ta_null_count": 0,
        "excluded_columns": {
            "target": target_excluded_columns,
            "context": context_excluded_columns,
        },
        "timestamp_min": timestamp_min.isoformat() if timestamp_min else None,
        "timestamp_max": timestamp_max.isoformat() if timestamp_max else None,
        "batches": batch_summaries,
    }
    manifest_path = root_output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))

    return MultiAssetAssemblyResult(
        target_asset=target_asset,
        context_assets=context_assets,
        context_hash=context_hash,
        root_key=root_key,
        root_id=layout.root_id,
        features_dir=features_dir,
        labels_dir=labels_dir,
        manifest_path=manifest_path,
        run_id=run_id,
        manifest=manifest,
    )


def _root_layout(root_key: str) -> Stage1RootLayout:
    try:
        return STAGE1_MULTIASSET_ROOT_LAYOUTS[root_key]
    except KeyError as exc:
        known = ", ".join(sorted(STAGE1_MULTIASSET_ROOT_LAYOUTS))
        raise ValueError(f"Unknown Stage-1 root {root_key!r}. Known roots: {known}") from exc


def _dedupe_assets(assets: Any) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for asset in assets:
        if asset in seen:
            continue
        seen.add(asset)
        out.append(asset)
    return tuple(out)


def _asset_slug(asset_id: str) -> str:
    return normalize_htf_asset_id(asset_id).lower()


def _asset_feature_dir(
    input_base_dir: Path,
    *,
    asset_id: str,
    layout: Stage1RootLayout,
    tf: str,
    feature_target_col: str,
) -> Path:
    return (
        Path(input_base_dir)
        / _asset_slug(asset_id)
        / layout.feature_root
        / tf
        / feature_target_col
    )


def _asset_label_dir(
    input_base_dir: Path,
    *,
    asset_id: str,
    layout: Stage1RootLayout,
    tf: str,
) -> Path:
    return Path(input_base_dir) / _asset_slug(asset_id) / layout.label_root / tf


def _batch_id_from_path(path: Path) -> int:
    stem = path.stem
    if not stem.startswith("batch_"):
        raise ValueError(f"Unexpected batch filename: {path.name}")
    return int(stem.removeprefix("batch_"))


def _batch_files(directory: Path) -> dict[int, Path]:
    if not directory.exists():
        raise FileNotFoundError(f"Batch directory not found: {directory}")
    files = sorted(directory.glob("batch_*.parquet"))
    if not files:
        raise FileNotFoundError(f"No batch_*.parquet files found in {directory}")
    return {_batch_id_from_path(path): path for path in files}


def _build_feature_index(
    asset_id: str,
    *,
    feature_dir: Path,
    target_col: str,
) -> AssetFeatureIndex:
    batch_paths = _batch_files(feature_dir)
    paths = [batch_paths[idx] for idx in sorted(batch_paths)]
    model_columns, excluded_columns = _model_column_intersection(paths, target_col)

    metas: list[FeatureFileMeta] = []
    timestamp_frames: list[pl.DataFrame] = []
    input_rows = 0
    for path in paths:
        ts_df = pl.read_parquet(path, columns=["timestamp"])
        row_count = len(ts_df)
        input_rows += row_count
        timestamp_frames.append(ts_df)
        metas.append(
            FeatureFileMeta(
                path=path,
                batch_id=_batch_id_from_path(path),
                row_count=row_count,
                timestamp_min=ts_df["timestamp"].min() if row_count else None,
                timestamp_max=ts_df["timestamp"].max() if row_count else None,
            )
        )

    all_timestamps = (
        pl.concat(timestamp_frames)
        if timestamp_frames
        else pl.DataFrame({"timestamp": []})
    )
    duplicate_count = _duplicate_count(all_timestamps, ["timestamp"])
    return AssetFeatureIndex(
        asset_id=normalize_htf_asset_id(asset_id),
        feature_dir=feature_dir,
        files=tuple(metas),
        model_columns=tuple(model_columns),
        excluded_model_columns=tuple(excluded_columns),
        duplicate_timestamp_count=duplicate_count,
        input_rows=input_rows,
    )


def _model_column_intersection(
    paths: list[Path],
    target_col: str,
) -> tuple[list[str], list[str]]:
    per_file_columns: list[set[str]] = []
    first_order: list[str] | None = None
    for path in paths:
        schema_df = pl.read_parquet(path, n_rows=0)
        cols = get_feature_columns(schema_df, target_col=target_col)
        if first_order is None:
            first_order = cols
        per_file_columns.append(set(cols))

    if not per_file_columns:
        return [], []
    shared = set.intersection(*per_file_columns)
    union = set.union(*per_file_columns)
    ordered = [col for col in (first_order or []) if col in shared]
    excluded = sorted(union - shared)
    return ordered, excluded


def _read_target_feature_batch(
    path: Path,
    *,
    asset_id: str,
    model_columns: tuple[str, ...],
    target_unprefixed_cols: tuple[str, ...],
    target_prefixed_cols: tuple[str, ...],
) -> pl.DataFrame:
    read_cols = ["timestamp", "batch_id", *model_columns]
    df = pl.read_parquet(path, columns=read_cols)
    prefix = f"T_{asset_id}__"
    return df.select(
        [
            pl.col("timestamp"),
            pl.col("batch_id"),
            *(pl.col(col) for col in target_unprefixed_cols),
            *(pl.col(col).alias(f"{prefix}{col}") for col in target_prefixed_cols),
        ]
    )


def _read_context_window(
    index: AssetFeatureIndex,
    *,
    timestamp_min: datetime,
    timestamp_max: datetime,
) -> pl.DataFrame:
    paths = index.overlapping_files(
        timestamp_min=timestamp_min,
        timestamp_max=timestamp_max,
    )
    output_columns = [
        "timestamp",
        *(f"C_{index.asset_id}__{col}" for col in index.model_columns),
    ]
    if not paths:
        return pl.DataFrame(
            schema={
                "timestamp": pl.Datetime(time_unit="us", time_zone="UTC"),
                **{col: pl.Float64 for col in output_columns if col != "timestamp"},
            }
        )

    df = pl.read_parquet(
        [str(path) for path in paths],
        columns=["timestamp", *index.model_columns],
    ).filter(
        pl.col("timestamp").is_between(
            timestamp_min,
            timestamp_max,
            closed="both",
        )
    )
    if _duplicate_count(df, ["timestamp"]):
        raise ValueError(
            f"Context {index.asset_id} has duplicate timestamps in overlapping "
            f"files for {timestamp_min} -> {timestamp_max}"
        )
    return df.select(
        [
            pl.col("timestamp"),
            *(
                pl.col(col).alias(f"C_{index.asset_id}__{col}")
                for col in index.model_columns
            ),
        ]
    )


def _ta_output_columns(
    *,
    project_root: Path,
    asset_id: str,
    role_prefix: str,
    ta_timeframes: tuple[str, ...],
    require: bool,
) -> list[str]:
    """Return prefixed TA flag columns for one asset/timeframe selection."""
    columns: list[str] = []
    for timeframe in ta_timeframes:
        path = ta_flags_path(project_root, asset_id, timeframe)
        if not path.exists():
            if require:
                raise FileNotFoundError(f"TA flag file not found: {path}")
            continue
        schema = pl.read_parquet(path, n_rows=0).schema
        columns.extend(f"{role_prefix}{col}" for col in ta_flag_columns(list(schema), timeframe))
    return columns


def _read_ta_window(
    *,
    project_root: Path,
    asset_id: str,
    role_prefix: str,
    ta_timeframes: tuple[str, ...],
    timestamp_min: datetime,
    timestamp_max: datetime,
) -> tuple[pl.DataFrame, list[str]]:
    """Read and prefix TA flags for one asset over a target timestamp window."""
    parts: list[pl.DataFrame] = []
    output_columns: list[str] = []
    for timeframe in ta_timeframes:
        path = ta_flags_path(project_root, asset_id, timeframe)
        if not path.exists():
            raise FileNotFoundError(f"TA flag file not found: {path}")
        schema = pl.read_parquet(path, n_rows=0).schema
        source_cols = ta_flag_columns(list(schema), timeframe)
        prefixed_cols = [f"{role_prefix}{col}" for col in source_cols]
        output_columns.extend(prefixed_cols)
        if not source_cols:
            continue
        frame = (
            pl.scan_parquet(path)
            .filter(pl.col("timestamp").is_between(timestamp_min, timestamp_max, closed="both"))
            .select(
                [
                    pl.col("timestamp"),
                    *(pl.col(col).alias(f"{role_prefix}{col}") for col in source_cols),
                ]
            )
            .collect()
        )
        parts.append(frame)

    if not output_columns:
        return pl.DataFrame({"timestamp": []}), []
    if not parts:
        return pl.DataFrame(
            schema={
                "timestamp": pl.Datetime(time_unit="us", time_zone="UTC"),
                **{col: pl.Int8 for col in output_columns},
            }
        ), output_columns
    out = parts[0]
    for part in parts[1:]:
        out = out.join(part, on="timestamp", how="outer_coalesce")
    if _duplicate_count(out, ["timestamp"]):
        raise ValueError(
            f"TA flags for {asset_id} have duplicate timestamps in "
            f"{timestamp_min} -> {timestamp_max}"
        )
    return out.sort("timestamp"), output_columns


def _join_ta_flags(
    df: pl.DataFrame,
    *,
    project_root: Path,
    asset_id: str,
    role_prefix: str,
    ta_timeframes: tuple[str, ...],
    timestamp_min: datetime,
    timestamp_max: datetime,
) -> pl.DataFrame:
    """Left-join TA flags and fill inactive/missing rows with zero."""
    ta_frame, ta_cols = _read_ta_window(
        project_root=project_root,
        asset_id=asset_id,
        role_prefix=role_prefix,
        ta_timeframes=ta_timeframes,
        timestamp_min=timestamp_min,
        timestamp_max=timestamp_max,
    )
    if not ta_cols:
        return df
    out = df.join(ta_frame, on="timestamp", how="left")
    return out.with_columns([pl.col(col).fill_null(0).cast(pl.Int8) for col in ta_cols])


def _ta_source_paths(
    *,
    project_root: Path,
    assets: tuple[str, ...],
    ta_timeframes: tuple[str, ...],
) -> dict[str, dict[str, str]]:
    """Return manifest-friendly TA source paths."""
    return {
        normalize_htf_asset_id(asset): {
            timeframe: str(ta_flags_path(project_root, asset, timeframe))
            for timeframe in ta_timeframes
        }
        for asset in assets
    }


def _read_target_labels_for_merged_rows(
    label_path: Path,
    *,
    merged: pl.DataFrame,
    target_col: str,
) -> pl.DataFrame:
    label_schema = pl.read_parquet(label_path, n_rows=0).schema
    label_cols = ["timestamp", "batch_id", target_col]
    target_name_col = f"{target_col}_name"
    if target_name_col in label_schema:
        label_cols.append(target_name_col)
    elif target_col == TARGET_COL and "target_name" in label_schema:
        label_cols.append("target_name")

    labels = pl.read_parquet(label_path, columns=label_cols)
    if _duplicate_count(labels, ["timestamp", "batch_id"]):
        raise ValueError(f"Duplicate label timestamp,batch_id rows in {label_path}")
    out = labels.join(
        merged.select(["timestamp", "batch_id"]),
        on=["timestamp", "batch_id"],
        how="inner",
    ).sort(["batch_id", "timestamp"])
    if len(out) != len(merged):
        raise ValueError(
            f"Merged rows do not have one target label each for {label_path}: "
            f"merged={len(merged)} labels={len(out)}"
        )
    return out


def _duplicate_count(df: pl.DataFrame, subset: list[str]) -> int:
    if df.is_empty():
        return 0
    return int(len(df) - df.select(subset).unique().height)


def _feature_null_count(df: pl.DataFrame, feature_columns: list[str]) -> int:
    if df.is_empty() or not feature_columns:
        return 0
    null_counts = df.select(
        [pl.col(col).is_null().sum().alias(col) for col in feature_columns]
    )
    return int(sum(null_counts.row(0)))


def _drop_null_feature_rows(
    df: pl.DataFrame,
    feature_columns: list[str],
) -> pl.DataFrame:
    """Remove rows that cannot satisfy the no-null model feature contract."""
    if df.is_empty() or not feature_columns:
        return df
    return df.filter(
        ~pl.any_horizontal([pl.col(col).is_null() for col in feature_columns])
    )


def _columns_with_nulls(df: pl.DataFrame, feature_columns: list[str]) -> list[str]:
    if df.is_empty() or not feature_columns:
        return []
    null_counts = df.select(
        [pl.col(col).is_null().sum().alias(col) for col in feature_columns]
    )
    row = null_counts.row(0, named=True)
    return [col for col, count in row.items() if int(count) > 0]


def _schema_hash(columns: list[str]) -> str:
    payload = "\n".join(columns)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _clear_generated_root(root_output_dir: Path) -> None:
    """Clear only the generated merged dataset root for one target/context/root."""
    if not root_output_dir.exists():
        return
    shutil.rmtree(root_output_dir)
