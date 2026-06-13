"""RPF-native data loading for walk-forward optimization."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.core.paths import FEATURE_SET


TARGET_VARIANT = "distance_horizon_vol_v2"
REGRESSION_LABEL_SUFFIX = "reg_distance_horizon_vol_v2"
VALID_COL = "target_reg_distance_valid_v2"
LABEL_WINDOW_COLS = (
    "label_window_start",
    "label_window_end",
    "label_window_batch_id",
    "target_reg_distance_horizon_minutes_v2",
)
DIAGNOSTIC_PREFIXES = ("rpf_align_",)
BATCH_RE = re.compile(r"batch_(\d+)\.parquet$")


@dataclass(frozen=True)
class RootLayout:
    root_key: str
    root_id: str
    label_root: str


ROOT_LAYOUTS: dict[str, RootLayout] = {
    "8h/B": RootLayout("8h/B", "8h_b", "htf_4class_labels"),
    "8h/C": RootLayout("8h/C", "8h_c", "htf_4class_labels_shift4h"),
    "24h/B": RootLayout("24h/B", "24h_b", "htf_4class_labels_24h"),
    "24h/C": RootLayout("24h/C", "24h_c", "htf_4class_labels_24h_shift12h"),
    "7d/B": RootLayout("7d/B", "7d_b", "htf_4class_labels_7d"),
    "7d/C": RootLayout("7d/C", "7d_c", "htf_4class_labels_7d_shift84h"),
}


@dataclass(frozen=True)
class RPFManifest:
    path: Path
    feature_columns: tuple[str, ...]
    feature_set: str
    root_id: str
    row_count: int
    feature_count: int
    duplicate_count: int
    null_feature_count: int
    source_fingerprint: str | None


@dataclass(frozen=True)
class RPFDataContext:
    project_root: Path
    data_root: Path
    asset: str
    root_key: str
    root_id: str
    target_col: str
    feature_root: Path
    label_root: Path
    manifest: RPFManifest


def resolve_context(
    *,
    project_root: Path,
    asset: str,
    root: str,
    target_col: str,
    data_root: Path | None = None,
) -> RPFDataContext:
    layout = root_layout(root)
    asset_slug = asset.lower()
    data_root = data_root or Path(project_root) / "data"
    feature_root = data_root / "htf_multiasset" / asset_slug / FEATURE_SET / layout.root_id / "1m"
    label_root = (
        data_root
        / "htf_multiasset"
        / asset_slug
        / f"{layout.label_root}_{REGRESSION_LABEL_SUFFIX}"
        / "1m"
    )
    manifest = load_rpf_manifest(feature_root / "manifest.json")
    return RPFDataContext(
        project_root=Path(project_root),
        data_root=Path(data_root),
        asset=asset.upper(),
        root_key=layout.root_key,
        root_id=layout.root_id,
        target_col=str(target_col),
        feature_root=feature_root,
        label_root=label_root,
        manifest=manifest,
    )


def root_layout(root: str) -> RootLayout:
    try:
        return ROOT_LAYOUTS[str(root)]
    except KeyError as exc:
        known = ", ".join(sorted(ROOT_LAYOUTS))
        raise ValueError(f"Unknown root {root!r}; expected one of: {known}") from exc


def load_rpf_manifest(path: Path) -> RPFManifest:
    if not path.exists():
        raise FileNotFoundError(f"RPF manifest not found: {path}")
    payload = json.loads(path.read_text())
    feature_columns = tuple(str(col) for col in payload.get("feature_columns", ()))
    if not feature_columns:
        raise ValueError(f"RPF manifest has no feature_columns: {path}")
    diagnostic = [col for col in feature_columns if col.startswith(DIAGNOSTIC_PREFIXES)]
    if diagnostic:
        raise ValueError(f"RPF manifest feature_columns include diagnostics: {diagnostic[:5]}")
    return RPFManifest(
        path=path,
        feature_columns=feature_columns,
        feature_set=str(payload.get("feature_set", "")),
        root_id=str(payload.get("root_id", "")),
        row_count=int(payload.get("row_count", 0)),
        feature_count=int(payload.get("feature_count", len(feature_columns))),
        duplicate_count=int(payload.get("duplicate_count", 0)),
        null_feature_count=int(payload.get("null_feature_count", 0)),
        source_fingerprint=payload.get("source_fingerprint"),
    )


def batch_id_from_path(path: Path) -> int:
    match = BATCH_RE.search(path.name)
    if not match:
        raise ValueError(f"Cannot parse batch id from path: {path}")
    return int(match.group(1))


def available_batch_ids(feature_root: Path, label_root: Path) -> tuple[int, ...]:
    feature_ids = {batch_id_from_path(path) for path in Path(feature_root).glob("batch_*.parquet")}
    label_ids = {batch_id_from_path(path) for path in Path(label_root).glob("batch_*.parquet")}
    return tuple(sorted(feature_ids & label_ids))


def build_batch_index(context: RPFDataContext) -> pl.DataFrame:
    batch_ids = available_batch_ids(context.feature_root, context.label_root)
    if not batch_ids:
        return _empty_batch_index()
    label_paths = [context.label_root / f"batch_{batch_id:04d}.parquet" for batch_id in batch_ids]
    feature_paths = [context.feature_root / f"batch_{batch_id:04d}.parquet" for batch_id in batch_ids]
    labels = (
        pl.scan_parquet(label_paths, extra_columns="ignore")
        .select(["timestamp", "batch_id", VALID_COL, context.target_col])
        .filter(
            pl.col(VALID_COL).fill_null(False)
            & pl.col(context.target_col).is_not_null()
            & pl.col(context.target_col).is_finite()
        )
    )
    features = pl.scan_parquet(feature_paths, extra_columns="ignore").select(["timestamp", "batch_id"])
    joined = labels.join(features, on=["timestamp", "batch_id"], how="inner")
    out = (
        joined.group_by("batch_id")
        .agg(
            pl.len().alias("valid_row_count"),
            pl.col("timestamp").min().alias("batch_start_ts"),
            pl.col("timestamp").max().alias("batch_end_ts"),
        )
        .sort("batch_id")
        .with_row_index("rpf_available_pos")
        .select(
            [
                pl.col("rpf_available_pos").cast(pl.Int64),
                pl.col("batch_id").cast(pl.Int64),
                "batch_start_ts",
                "batch_end_ts",
                pl.col("valid_row_count").cast(pl.Int64),
            ]
        )
        .collect()
    )
    return out


def build_label_window_index(context: RPFDataContext, batch_ids: tuple[int, ...] | list[int] | None = None) -> pl.DataFrame:
    batch_ids = tuple(int(value) for value in (batch_ids or available_batch_ids(context.feature_root, context.label_root)))
    if not batch_ids:
        return _empty_label_window_index()
    label_paths = [context.label_root / f"batch_{batch_id:04d}.parquet" for batch_id in batch_ids]
    frame = (
        pl.scan_parquet(label_paths, extra_columns="ignore")
        .select(["timestamp", "batch_id", VALID_COL, context.target_col, *LABEL_WINDOW_COLS])
        .filter(
            pl.col(VALID_COL).fill_null(False)
            & pl.col(context.target_col).is_not_null()
            & pl.col(context.target_col).is_finite()
            & pl.col("label_window_start").is_not_null()
            & pl.col("label_window_end").is_not_null()
            & pl.col("label_window_batch_id").is_not_null()
        )
        .group_by("batch_id")
        .agg(
            pl.len().alias("label_valid_row_count"),
            pl.col("timestamp").min().alias("entry_start_ts"),
            pl.col("timestamp").max().alias("entry_end_ts"),
            pl.col("label_window_start").min().alias("label_window_start_min"),
            pl.col("label_window_end").max().alias("label_window_end_max"),
            pl.col("label_window_batch_id").min().alias("label_window_batch_id_min"),
            pl.col("label_window_batch_id").max().alias("label_window_batch_id_max"),
            (pl.col("label_window_batch_id") != pl.col("batch_id")).sum().alias("cross_batch_label_count"),
            pl.col("target_reg_distance_horizon_minutes_v2").min().alias("horizon_minutes_min"),
            pl.col("target_reg_distance_horizon_minutes_v2").max().alias("horizon_minutes_max"),
        )
        .sort("batch_id")
        .select(
            [
                pl.col("batch_id").cast(pl.Int64),
                pl.col("label_valid_row_count").cast(pl.Int64),
                "entry_start_ts",
                "entry_end_ts",
                "label_window_start_min",
                "label_window_end_max",
                pl.col("label_window_batch_id_min").cast(pl.Int64),
                pl.col("label_window_batch_id_max").cast(pl.Int64),
                pl.col("cross_batch_label_count").cast(pl.Int64),
                pl.col("horizon_minutes_min").cast(pl.Float64),
                pl.col("horizon_minutes_max").cast(pl.Float64),
            ]
        )
        .collect()
    )
    return frame


def load_joined_batches(
    context: RPFDataContext,
    batch_ids: tuple[int, ...] | list[int],
    *,
    feature_columns: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    if not batch_ids:
        raise ValueError("No batch ids requested")
    feature_columns = feature_columns or context.manifest.feature_columns
    missing = [col for col in feature_columns if col not in context.manifest.feature_columns]
    if missing:
        raise ValueError(f"Requested columns not present in RPF manifest: {missing[:5]}")
    frames: list[pl.DataFrame] = []
    for batch_id in sorted({int(value) for value in batch_ids}):
        feature_path = context.feature_root / f"batch_{batch_id:04d}.parquet"
        label_path = context.label_root / f"batch_{batch_id:04d}.parquet"
        if not feature_path.exists() or not label_path.exists():
            raise FileNotFoundError(f"Missing feature or label batch for {batch_id}")
        features = pl.read_parquet(feature_path, columns=["timestamp", "batch_id", *feature_columns])
        labels = pl.read_parquet(label_path, columns=["timestamp", "batch_id", VALID_COL, context.target_col])
        joined = (
            labels.join(features, on=["timestamp", "batch_id"], how="inner")
            .filter(
                pl.col(VALID_COL).fill_null(False)
                & pl.col(context.target_col).is_not_null()
                & pl.col(context.target_col).is_finite()
            )
            .drop(VALID_COL)
        )
        frames.append(joined)
    out = pl.concat(frames, how="vertical") if frames else pl.DataFrame()
    if out.is_empty():
        raise ValueError(f"Joined RPF batches are empty: {batch_ids}")
    return out.sort(["batch_id", "timestamp"])


def frame_to_numpy(
    frame: pl.DataFrame,
    *,
    target_col: str,
    feature_columns: tuple[str, ...] | list[str],
) -> tuple[np.ndarray, np.ndarray, pl.DataFrame]:
    cols = list(feature_columns)
    model_frame = frame.select(["timestamp", "batch_id", target_col, *cols]).drop_nulls([target_col, *cols])
    X = model_frame.select(cols).to_numpy().astype("float64")
    y = model_frame[target_col].to_numpy().astype("float64")
    mask = np.isfinite(y) & np.isfinite(X).all(axis=1)
    meta = (
        model_frame.select(["timestamp", "batch_id"])
        .with_columns(pl.Series("_model_row_mask", mask))
        .filter(pl.col("_model_row_mask"))
        .drop("_model_row_mask")
    )
    return X[mask], y[mask], meta


def _empty_batch_index() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rpf_available_pos": pl.Int64,
            "batch_id": pl.Int64,
            "batch_start_ts": pl.Datetime(time_zone="UTC"),
            "batch_end_ts": pl.Datetime(time_zone="UTC"),
            "valid_row_count": pl.Int64,
        }
    )


def _empty_label_window_index() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "batch_id": pl.Int64,
            "label_valid_row_count": pl.Int64,
            "entry_start_ts": pl.Datetime(time_zone="UTC"),
            "entry_end_ts": pl.Datetime(time_zone="UTC"),
            "label_window_start_min": pl.Datetime(time_zone="UTC"),
            "label_window_end_max": pl.Datetime(time_zone="UTC"),
            "label_window_batch_id_min": pl.Int64,
            "label_window_batch_id_max": pl.Int64,
            "cross_batch_label_count": pl.Int64,
            "horizon_minutes_min": pl.Float64,
            "horizon_minutes_max": pl.Float64,
        }
    )
