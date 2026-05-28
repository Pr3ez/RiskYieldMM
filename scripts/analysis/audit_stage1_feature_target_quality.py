from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from scripts.analysis.materialize_stage1_regression_targets import (  # noqa: E402
    DOWN_EXTREME_COL,
    DOWN_MEAN_LOW_COL,
    RAW_DISTANCE_COLS,
    REGRESSION_VARIANT,
    UP_EXTREME_COL,
    UP_MEAN_HIGH_COL,
    VALID_COL,
    normalize_variant,
)
from scripts.feature_engineering.htf_asset_registry import normalize_htf_asset_id  # noqa: E402
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (  # noqa: E402
    FEATURE_TARGET_COL,
    MULTIASSET_MERGED_ROOT,
    REG_DISTANCE_VOL_V1_LABEL_SUFFIX,
    STAGE1_MULTIASSET_ROOT_LAYOUTS,
    build_context_set_hash,
    build_stage1_dataset_variant_id,
    parse_stage1_context_assets,
)
from scripts.project_paths import ensure_project_root_on_path  # noqa: E402


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
TF = "1m"
TARGET_COLS = (UP_EXTREME_COL, UP_MEAN_HIGH_COL, DOWN_MEAN_LOW_COL, DOWN_EXTREME_COL)
TARGET_RAW_PAIRS = tuple(zip(TARGET_COLS, RAW_DISTANCE_COLS, strict=True))
TARGET_DIAGNOSTIC_COLS = (
    VALID_COL,
    "target_reg_distance_reason_v1",
    "target_reg_distance_future_bars_v1",
    "tb_volatility_pct",
    "tb_atr_pct_14",
    "tb_realized_vol_120",
    *TARGET_COLS,
    *RAW_DISTANCE_COLS,
)
LEAKAGE_NAME_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(^|__)target_",
        r"(^|__)tb_",
        r"label_window",
        r"future",
        r"diagnostic",
        r"max_high_offset",
        r"min_low_offset",
        r"max_high_ts",
        r"min_low_ts",
    )
)


@dataclass(frozen=True)
class AuditPaths:
    manifest_path: Path
    features_dir: Path
    source_label_dir: Path
    batch_index_path: Path | None


@dataclass(frozen=True)
class AuditResult:
    status: str
    report_path: Path | None
    output_dir: Path
    summary: dict[str, Any]
    issues: pl.DataFrame
    feature_quality: pl.DataFrame
    target_quality: pl.DataFrame
    correlations: pl.DataFrame
    duplicate_groups: pl.DataFrame


class OnlineFeatureStats:
    """Streaming per-feature quality statistics for numeric model inputs."""

    def __init__(self, feature_cols: list[str]) -> None:
        self.feature_cols = feature_cols
        n = len(feature_cols)
        self.rows = 0
        self.nulls = np.zeros(n, dtype=np.int64)
        self.nonfinite = np.zeros(n, dtype=np.int64)
        self.finite_n = np.zeros(n, dtype=np.int64)
        self.zeros = np.zeros(n, dtype=np.int64)
        self.sum = np.zeros(n, dtype=np.float64)
        self.sumsq = np.zeros(n, dtype=np.float64)
        self.min = np.full(n, np.inf, dtype=np.float64)
        self.max = np.full(n, -np.inf, dtype=np.float64)
        self.max_abs = np.zeros(n, dtype=np.float64)

    def update(self, df: pl.DataFrame, x: np.ndarray) -> None:
        self.rows += int(x.shape[0])
        if x.size == 0:
            return
        self.nulls += _null_counts(df, self.feature_cols)
        finite = np.isfinite(x)
        self.nonfinite += (~finite).sum(axis=0)
        self.finite_n += finite.sum(axis=0)
        self.zeros += ((x == 0.0) & finite).sum(axis=0)
        safe = np.where(finite, x, 0.0)
        self.sum += safe.sum(axis=0)
        self.sumsq += (safe * safe).sum(axis=0)
        self.min = np.minimum(self.min, np.where(finite, x, np.inf).min(axis=0))
        self.max = np.maximum(self.max, np.where(finite, x, -np.inf).max(axis=0))
        self.max_abs = np.maximum(self.max_abs, np.abs(safe).max(axis=0))

    def to_frame(self, sample_quantiles: dict[str, dict[str, float]], sample_unique: dict[str, int]) -> pl.DataFrame:
        rows: list[dict[str, Any]] = []
        for i, feature in enumerate(self.feature_cols):
            finite_n = int(self.finite_n[i])
            mean = float(self.sum[i] / finite_n) if finite_n else None
            variance = None
            std = None
            if finite_n:
                variance = max(float(self.sumsq[i] / finite_n - (self.sum[i] / finite_n) ** 2), 0.0)
                std = math.sqrt(variance)
            min_value = None if finite_n == 0 else float(self.min[i])
            max_value = None if finite_n == 0 else float(self.max[i])
            zero_rate = float(self.zeros[i] / finite_n) if finite_n else None
            constant = bool(finite_n > 0 and min_value == max_value)
            near_constant = bool(
                constant
                or (std is not None and std <= 1e-12)
                or (zero_rate is not None and zero_rate >= 0.995)
                or (sample_unique.get(feature, 999999) <= 2)
            )
            q = sample_quantiles.get(feature, {})
            rows.append(
                {
                    "feature": feature,
                    "asset_role": _feature_asset_role(feature),
                    "feature_family": _feature_family(feature),
                    "rows_seen": int(self.rows),
                    "finite_rows": finite_n,
                    "null_count": int(self.nulls[i]),
                    "nonfinite_count": int(self.nonfinite[i]),
                    "min": min_value,
                    "p01_sample": q.get("p01"),
                    "p50_sample": q.get("p50"),
                    "p99_sample": q.get("p99"),
                    "max": max_value,
                    "mean": mean,
                    "std": std,
                    "zero_rate": zero_rate,
                    "sample_unique_count": int(sample_unique.get(feature, 0)),
                    "max_abs": float(self.max_abs[i]),
                    "constant": constant,
                    "near_constant": near_constant,
                    "extreme_abs_ge_1e6": bool(float(self.max_abs[i]) >= 1_000_000.0),
                }
            )
        return pl.DataFrame(rows)


class OnlinePearson:
    """Streaming Pearson correlation for every target/feature pair."""

    def __init__(self, target_cols: tuple[str, ...], feature_cols: list[str]) -> None:
        self.target_cols = target_cols
        self.feature_cols = feature_cols
        shape = (len(target_cols), len(feature_cols))
        self.n = np.zeros(shape, dtype=np.float64)
        self.sum_x = np.zeros(shape, dtype=np.float64)
        self.sum_y = np.zeros(shape, dtype=np.float64)
        self.sum_x2 = np.zeros(shape, dtype=np.float64)
        self.sum_y2 = np.zeros(shape, dtype=np.float64)
        self.sum_xy = np.zeros(shape, dtype=np.float64)

    def update(self, x: np.ndarray, y: np.ndarray) -> None:
        if x.size == 0 or y.size == 0:
            return
        x_finite = np.isfinite(x)
        for target_idx in range(len(self.target_cols)):
            target_values = y[:, target_idx]
            y_finite = np.isfinite(target_values)
            mask = x_finite & y_finite[:, None]
            if not mask.any():
                continue
            x_safe = np.where(mask, x, 0.0)
            y_matrix = np.where(mask, target_values[:, None], 0.0)
            self.n[target_idx] += mask.sum(axis=0)
            self.sum_x[target_idx] += x_safe.sum(axis=0)
            self.sum_y[target_idx] += y_matrix.sum(axis=0)
            self.sum_x2[target_idx] += (x_safe * x_safe).sum(axis=0)
            self.sum_y2[target_idx] += (y_matrix * y_matrix).sum(axis=0)
            self.sum_xy[target_idx] += (x_safe * y_matrix).sum(axis=0)

    def correlations(self) -> np.ndarray:
        numerator = self.n * self.sum_xy - self.sum_x * self.sum_y
        denom_x = self.n * self.sum_x2 - self.sum_x * self.sum_x
        denom_y = self.n * self.sum_y2 - self.sum_y * self.sum_y
        denominator = np.sqrt(np.maximum(denom_x, 0.0) * np.maximum(denom_y, 0.0))
        out = np.full_like(numerator, np.nan, dtype=np.float64)
        valid = (self.n >= 2) & (denominator > 0)
        out[valid] = numerator[valid] / denominator[valid]
        return out

    def to_rows(self, *, segment: int | None = None) -> list[dict[str, Any]]:
        corr = self.correlations()
        rows: list[dict[str, Any]] = []
        for target_idx, target_col in enumerate(self.target_cols):
            for feature_idx, feature in enumerate(self.feature_cols):
                value = corr[target_idx, feature_idx]
                row = {
                    "target_col": target_col,
                    "feature": feature,
                    "pearson": _finite_or_none(value),
                    "pearson_n": int(self.n[target_idx, feature_idx]),
                    "abs_pearson": _finite_or_none(abs(value)),
                }
                if segment is not None:
                    row["segment"] = int(segment)
                rows.append(row)
        return rows


def run_quality_audit(
    *,
    project_root: Path,
    target_asset: str,
    context_assets: tuple[str, ...],
    root_key: str,
    regression_variant: str,
    merged_target_col: str,
    multiasset_dataset_dir: Path | None = None,
    output_dir: Path | None = None,
    report_path: Path | None = None,
    write_report: bool = False,
    sample_rows: int = 20_000,
    stability_segments: int = 5,
) -> AuditResult:
    """Run a read-only quality audit over one merged Stage-1 dataset."""
    normalize_variant(regression_variant)
    project_root = Path(project_root)
    paths = resolve_audit_paths(
        project_root=project_root,
        target_asset=target_asset,
        context_assets=context_assets,
        root_key=root_key,
        merged_target_col=merged_target_col,
        multiasset_dataset_dir=multiasset_dataset_dir,
    )
    manifest = json.loads(paths.manifest_path.read_text())
    feature_cols = list(manifest.get("feature_columns") or [])
    if not feature_cols:
        feature_cols = _feature_columns_from_first_batch(paths.features_dir)
    if merged_target_col not in TARGET_COLS:
        raise ValueError(f"merged_target_col must be one of {TARGET_COLS}; got {merged_target_col}")

    output_dir = output_dir or (
        project_root
        / "test_output"
        / "stage1_feature_target_quality_audit"
        / f"{normalize_htf_asset_id(target_asset).lower()}_{_root_slug(root_key)}_{regression_variant}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    batch_index = _read_batch_index(paths.batch_index_path)
    feature_stats = OnlineFeatureStats(feature_cols)
    pearson = OnlinePearson(TARGET_COLS, feature_cols)
    segment_accumulators = [OnlinePearson(TARGET_COLS, feature_cols) for _ in range(stability_segments)]
    sample_x: list[np.ndarray] = []
    sample_y: list[np.ndarray] = []
    sample_seen = 0
    issues: list[dict[str, Any]] = []
    target_acc = _new_target_accumulator()
    schema_problem_batches = 0
    duplicate_ts_batch = 0
    rows_seen = 0
    joined_rows = 0
    missing_label_rows = 0

    feature_files = sorted(paths.features_dir.glob("batch_*.parquet"))
    if not feature_files:
        raise FileNotFoundError(f"No merged feature batches found in {paths.features_dir}")

    for feature_path in feature_files:
        batch_id = _batch_id_from_path(feature_path)
        if batch_id is None:
            continue
        label_path = paths.source_label_dir / f"batch_{batch_id:04d}.parquet"
        if not label_path.exists():
            issues.append(_issue("critical", "target", "missing_source_label_batch", str(label_path)))
            continue
        feature_df = pl.read_parquet(feature_path)
        missing_features = [col for col in feature_cols if col not in feature_df.columns]
        if missing_features:
            schema_problem_batches += 1
            issues.append(
                _issue(
                    "critical",
                    "feature",
                    "schema_missing_features",
                    f"batch={batch_id} missing={missing_features[:10]}",
                    batch_id=batch_id,
                )
            )
            continue
        dup_count = feature_df.select(pl.struct(["timestamp", "batch_id"]).is_duplicated().sum()).item()
        duplicate_ts_batch += int(dup_count)
        label_cols = [col for col in ("timestamp", "batch_id", *TARGET_DIAGNOSTIC_COLS) if col in pl.read_parquet_schema(label_path)]
        label_df = pl.read_parquet(label_path, columns=label_cols)
        joined = feature_df.select(["timestamp", "batch_id", *feature_cols]).join(
            label_df.select(label_cols),
            on=["timestamp", "batch_id"],
            how="left",
        )
        rows_seen += feature_df.height
        joined_rows += joined.height
        missing_label_rows += int(joined.select(pl.col(VALID_COL).is_null().sum()).item()) if VALID_COL in joined.columns else joined.height

        x = _numeric_matrix(joined, feature_cols)
        y = _target_matrix(joined)
        feature_stats.update(joined, x)
        pearson.update(x, y)
        segment = _batch_segment(batch_id, batch_index, stability_segments)
        segment_accumulators[segment].update(x, y)
        _update_target_accumulator(target_acc, joined)

        if sample_seen < sample_rows:
            take = min(int(sample_rows - sample_seen), joined.height)
            if take > 0:
                sample_x.append(x[:take].astype(np.float32, copy=True))
                sample_y.append(y[:take].astype(np.float64, copy=True))
                sample_seen += take

    sample_x_arr = np.vstack(sample_x) if sample_x else np.empty((0, len(feature_cols)), dtype=np.float32)
    sample_y_arr = np.vstack(sample_y) if sample_y else np.empty((0, len(TARGET_COLS)), dtype=np.float64)
    sample_quantiles, sample_unique = _sample_feature_profiles(sample_x_arr, feature_cols)
    feature_quality = feature_stats.to_frame(sample_quantiles, sample_unique)
    target_quality = _target_quality_frame(target_acc)
    correlations = _correlation_frame(pearson, sample_x_arr, sample_y_arr, feature_cols)
    stability = pl.DataFrame(
        [
            row
            for segment, accumulator in enumerate(segment_accumulators)
            for row in accumulator.to_rows(segment=segment)
        ]
    )
    duplicate_groups = _duplicate_feature_groups(sample_x_arr, feature_cols)
    issues.extend(_quality_issues(feature_quality, target_quality, correlations, duplicate_groups))
    issues.extend(_leakage_name_issues(feature_cols))
    issues.append(
        _issue(
            "warning",
            "target",
            "distance_vol_v1_scale_design",
            "distance_vol_v1 divides multi-hour future excursions by short-horizon prediction-time volatility; "
            "large normalized values can be arithmetically valid but poorly scaled.",
        )
    )
    if schema_problem_batches:
        issues.append(_issue("critical", "feature", "schema_inconsistent_batches", str(schema_problem_batches)))
    if duplicate_ts_batch:
        issues.append(_issue("critical", "feature", "duplicate_timestamp_batch_rows", str(duplicate_ts_batch)))
    if missing_label_rows:
        issues.append(_issue("critical", "target", "missing_joined_source_labels", str(missing_label_rows)))

    issues_df = pl.DataFrame(issues) if issues else _empty_issues_frame()
    status = _status_from_issues(issues_df)
    manifest_summary = {
        "manifest_path": str(paths.manifest_path),
        "target_asset": normalize_htf_asset_id(target_asset),
        "context_assets": list(context_assets),
        "root": root_key,
        "regression_variant": regression_variant,
        "merged_target_col": merged_target_col,
        "feature_rows_seen": int(rows_seen),
        "joined_rows": int(joined_rows),
        "feature_columns_count": int(len(feature_cols)),
        "source_label_dir": str(paths.source_label_dir),
        "sample_rows": int(sample_x_arr.shape[0]),
        "stability_segments": int(stability_segments),
        "status": status,
        "issue_counts": dict(Counter(issues_df["severity"].to_list())) if not issues_df.is_empty() else {},
    }

    feature_quality.write_parquet(output_dir / "feature_quality.parquet")
    target_quality.write_parquet(output_dir / "target_quality.parquet")
    correlations.write_parquet(output_dir / "feature_target_correlations.parquet")
    stability.write_parquet(output_dir / "correlation_stability.parquet")
    duplicate_groups.write_parquet(output_dir / "duplicate_feature_groups.parquet")
    issues_df.write_parquet(output_dir / "issues.parquet")
    (output_dir / "audit_summary.json").write_text(
        json.dumps(manifest_summary, indent=2, default=str)
    )

    written_report: Path | None = None
    if write_report:
        written_report = report_path or _default_report_path(
            project_root,
            target_asset=target_asset,
            root_key=root_key,
            regression_variant=regression_variant,
        )
        _write_markdown_report(
            written_report,
            summary=manifest_summary,
            manifest=manifest,
            issues=issues_df,
            feature_quality=feature_quality,
            target_quality=target_quality,
            correlations=correlations,
            duplicate_groups=duplicate_groups,
            output_dir=output_dir,
        )

    return AuditResult(
        status=status,
        report_path=written_report,
        output_dir=output_dir,
        summary=manifest_summary,
        issues=issues_df,
        feature_quality=feature_quality,
        target_quality=target_quality,
        correlations=correlations,
        duplicate_groups=duplicate_groups,
    )


def resolve_audit_paths(
    *,
    project_root: Path,
    target_asset: str,
    context_assets: tuple[str, ...],
    root_key: str,
    merged_target_col: str,
    multiasset_dataset_dir: Path | None = None,
) -> AuditPaths:
    target_asset = normalize_htf_asset_id(target_asset)
    layout = STAGE1_MULTIASSET_ROOT_LAYOUTS[root_key]
    context_hash = build_context_set_hash(
        target_asset=target_asset,
        context_assets=context_assets,
    )
    variant_id = build_stage1_dataset_variant_id(
        target_col=merged_target_col,
        include_ta_flags=False,
    )
    dataset_dir = Path(multiasset_dataset_dir or project_root / "data" / MULTIASSET_MERGED_ROOT)
    root_dir = dataset_dir / target_asset.lower() / context_hash
    if variant_id != "base":
        root_dir = root_dir / variant_id
    root_dir = root_dir / layout.root_id
    manifest_path = root_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Merged dataset manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    features_dir = Path(manifest["output_paths"]["features_dir"]) / TF / FEATURE_TARGET_COL
    batch_index_path = Path(manifest["output_paths"].get("stage1_batch_index", ""))
    source_label_dir = (
        project_root
        / "data"
        / "htf_multiasset"
        / target_asset.lower()
        / f"{layout.label_root}_{REG_DISTANCE_VOL_V1_LABEL_SUFFIX}"
        / TF
    )
    if not features_dir.exists():
        raise FileNotFoundError(f"Merged feature directory not found: {features_dir}")
    if not source_label_dir.exists():
        raise FileNotFoundError(f"Regression source label directory not found: {source_label_dir}")
    return AuditPaths(
        manifest_path=manifest_path,
        features_dir=features_dir,
        source_label_dir=source_label_dir,
        batch_index_path=batch_index_path if batch_index_path.exists() else None,
    )


def detect_leakage_feature_names(feature_cols: list[str]) -> list[dict[str, Any]]:
    """Return suspicious feature names that look like labels or future diagnostics."""
    out: list[dict[str, Any]] = []
    for feature in feature_cols:
        base = feature.split("__", 1)[-1]
        for pattern in LEAKAGE_NAME_PATTERNS:
            if pattern.search(feature) or pattern.search(base):
                out.append(
                    {
                        "feature": feature,
                        "pattern": pattern.pattern,
                    }
                )
                break
    return out


def _numeric_matrix(df: pl.DataFrame, columns: list[str]) -> np.ndarray:
    if not columns:
        return np.empty((df.height, 0), dtype=np.float64)
    return (
        df.select([pl.col(col).cast(pl.Float64, strict=False).alias(col) for col in columns])
        .to_numpy()
        .astype(np.float64, copy=False)
    )


def _target_matrix(df: pl.DataFrame) -> np.ndarray:
    cols = [col for col in TARGET_COLS if col in df.columns]
    if len(cols) != len(TARGET_COLS):
        missing = sorted(set(TARGET_COLS) - set(cols))
        raise ValueError(f"Joined labels are missing regression target columns: {missing}")
    return _numeric_matrix(df, list(TARGET_COLS))


def _null_counts(df: pl.DataFrame, columns: list[str]) -> np.ndarray:
    if not columns:
        return np.array([], dtype=np.int64)
    row = df.select([pl.col(col).is_null().sum().alias(col) for col in columns]).to_dicts()[0]
    return np.array([int(row[col]) for col in columns], dtype=np.int64)


def _sample_feature_profiles(x: np.ndarray, feature_cols: list[str]) -> tuple[dict[str, dict[str, float]], dict[str, int]]:
    quantiles: dict[str, dict[str, float]] = {}
    unique_counts: dict[str, int] = {}
    if x.size == 0:
        return quantiles, unique_counts
    for idx, feature in enumerate(feature_cols):
        values = x[:, idx].astype(np.float64, copy=False)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            unique_counts[feature] = 0
            continue
        quantiles[feature] = {
            "p01": float(np.quantile(finite, 0.01)),
            "p50": float(np.quantile(finite, 0.50)),
            "p99": float(np.quantile(finite, 0.99)),
        }
        unique_counts[feature] = int(min(np.unique(finite).size, 1_000_000))
    return quantiles, unique_counts


def _new_target_accumulator() -> dict[str, Any]:
    return {
        "rows": 0,
        "valid_rows": 0,
        "invalid_rows": 0,
        "valid_null": defaultdict(int),
        "invalid_nonnull": defaultdict(int),
        "nonfinite": defaultdict(int),
        "negative": defaultdict(int),
        "zeros": defaultdict(int),
        "tails": defaultdict(lambda: defaultdict(int)),
        "values": defaultdict(list),
        "raw_values": defaultdict(list),
        "vol_values": [],
        "vol_floor_count": 0,
        "bad_norm": defaultdict(int),
        "reason_counts": Counter(),
    }


def _update_target_accumulator(acc: dict[str, Any], df: pl.DataFrame) -> None:
    rows = df.height
    acc["rows"] += rows
    valid = df[VALID_COL].fill_null(False).to_numpy().astype(bool)
    acc["valid_rows"] += int(valid.sum())
    acc["invalid_rows"] += int((~valid).sum())
    if "target_reg_distance_reason_v1" in df.columns:
        acc["reason_counts"].update(str(v) for v in df["target_reg_distance_reason_v1"].fill_null("missing").to_list())
    vol = _numeric_matrix(df, ["tb_volatility_pct"])[:, 0] if "tb_volatility_pct" in df.columns else np.full(rows, np.nan)
    valid_vol = vol[valid & np.isfinite(vol)]
    if valid_vol.size:
        acc["vol_values"].append(valid_vol.astype(np.float64, copy=True))
        acc["vol_floor_count"] += int((valid_vol <= 0.000500001).sum())
    for target, raw in TARGET_RAW_PAIRS:
        target_values = _numeric_matrix(df, [target])[:, 0]
        raw_values = _numeric_matrix(df, [raw])[:, 0] if raw in df.columns else np.full(rows, np.nan)
        target_valid = target_values[valid]
        raw_valid = raw_values[valid]
        finite = np.isfinite(target_valid)
        acc["valid_null"][target] += int(np.isnan(target_valid).sum())
        acc["invalid_nonnull"][target] += int(np.isfinite(target_values[~valid]).sum())
        acc["nonfinite"][target] += int((~finite).sum())
        acc["negative"][target] += int((target_valid[finite] < 0).sum())
        acc["zeros"][target] += int((target_valid[finite] == 0).sum())
        for threshold in (5, 10, 25, 50, 100):
            acc["tails"][target][f"ge_{threshold}"] += int((target_valid[finite] >= threshold).sum())
        if finite.any():
            acc["values"][target].append(target_valid[finite].astype(np.float64, copy=True))
        raw_finite = raw_valid[np.isfinite(raw_valid)]
        if raw_finite.size:
            acc["raw_values"][raw].append(raw_finite.astype(np.float64, copy=True))
        norm_ok = valid & np.isfinite(target_values) & np.isfinite(raw_values) & np.isfinite(vol) & (vol > 0)
        if norm_ok.any():
            bad = np.abs(target_values[norm_ok] - raw_values[norm_ok] / vol[norm_ok]) > 1e-9
            acc["bad_norm"][target] += int(bad.sum())


def _target_quality_frame(acc: dict[str, Any]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    vol_values = np.concatenate(acc["vol_values"]) if acc["vol_values"] else np.array([], dtype=np.float64)
    for target, raw in TARGET_RAW_PAIRS:
        values = np.concatenate(acc["values"][target]) if acc["values"][target] else np.array([], dtype=np.float64)
        raw_values = np.concatenate(acc["raw_values"][raw]) if acc["raw_values"][raw] else np.array([], dtype=np.float64)
        row = {
            "target_col": target,
            "raw_col": raw,
            "rows_seen": int(acc["rows"]),
            "valid_rows": int(values.size),
            "valid_null_count": int(acc["valid_null"][target]),
            "invalid_nonnull_count": int(acc["invalid_nonnull"][target]),
            "nonfinite_count": int(acc["nonfinite"][target]),
            "negative_count": int(acc["negative"][target]),
            "bad_norm_count": int(acc["bad_norm"][target]),
            "zero_rate": float(acc["zeros"][target] / values.size) if values.size else None,
            "tail_ge_5": int(acc["tails"][target]["ge_5"]),
            "tail_ge_10": int(acc["tails"][target]["ge_10"]),
            "tail_ge_25": int(acc["tails"][target]["ge_25"]),
            "tail_ge_50": int(acc["tails"][target]["ge_50"]),
            "tail_ge_100": int(acc["tails"][target]["ge_100"]),
            "vol_floor_count": int(acc["vol_floor_count"]),
            "vol_floor_rate": float(acc["vol_floor_count"] / values.size) if values.size else None,
        }
        row.update(_distribution_fields(values, prefix="target"))
        row.update(_distribution_fields(raw_values, prefix="raw_pct"))
        row.update(_distribution_fields(vol_values, prefix="vol_pct"))
        rows.append(row)
    return pl.DataFrame(rows)


def _distribution_fields(values: np.ndarray, *, prefix: str) -> dict[str, Any]:
    if values.size == 0:
        return {
            f"{prefix}_min": None,
            f"{prefix}_p50": None,
            f"{prefix}_p95": None,
            f"{prefix}_p99": None,
            f"{prefix}_p999": None,
            f"{prefix}_max": None,
            f"{prefix}_mean": None,
        }
    return {
        f"{prefix}_min": float(np.min(values)),
        f"{prefix}_p50": float(np.quantile(values, 0.50)),
        f"{prefix}_p95": float(np.quantile(values, 0.95)),
        f"{prefix}_p99": float(np.quantile(values, 0.99)),
        f"{prefix}_p999": float(np.quantile(values, 0.999)),
        f"{prefix}_max": float(np.max(values)),
        f"{prefix}_mean": float(np.mean(values)),
    }


def _correlation_frame(
    pearson: OnlinePearson,
    sample_x: np.ndarray,
    sample_y: np.ndarray,
    feature_cols: list[str],
) -> pl.DataFrame:
    rows = pearson.to_rows()
    spearman = _sample_spearman_matrix(sample_x, sample_y)
    if spearman.size:
        row_idx = 0
        for target_idx in range(len(TARGET_COLS)):
            for _feature_idx, _feature in enumerate(feature_cols):
                value = spearman[target_idx, _feature_idx]
                rows[row_idx]["spearman_sample"] = _finite_or_none(value)
                rows[row_idx]["abs_spearman_sample"] = _finite_or_none(abs(value))
                row_idx += 1
    else:
        for row in rows:
            row["spearman_sample"] = None
            row["abs_spearman_sample"] = None
    return pl.DataFrame(rows).sort(["target_col", "abs_pearson"], descending=[False, True])


def _sample_spearman_matrix(sample_x: np.ndarray, sample_y: np.ndarray) -> np.ndarray:
    if sample_x.size == 0 or sample_y.size == 0:
        return np.empty((0, 0), dtype=np.float64)
    out = np.full((sample_y.shape[1], sample_x.shape[1]), np.nan, dtype=np.float64)
    for target_idx in range(sample_y.shape[1]):
        y = sample_y[:, target_idx].astype(np.float64, copy=False)
        y_mask = np.isfinite(y)
        if y_mask.sum() < 3:
            continue
        for feature_idx in range(sample_x.shape[1]):
            x = sample_x[:, feature_idx].astype(np.float64, copy=False)
            mask = y_mask & np.isfinite(x)
            if mask.sum() < 3:
                continue
            out[target_idx, feature_idx] = _pearson(_rank_average(x[mask]), _rank_average(y[mask]))
    return out


def _rank_average(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and sorted_values[j] == sorted_values[i]:
            j += 1
        ranks[order[i:j]] = (i + j - 1) / 2.0 + 1.0
        i = j
    return ranks


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2 or float(np.std(a)) == 0.0 or float(np.std(b)) == 0.0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _duplicate_feature_groups(sample_x: np.ndarray, feature_cols: list[str]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    if sample_x.size == 0:
        return pl.DataFrame({"group_kind": [], "group_hash": [], "features": [], "feature_count": []})
    for kind, decimals in (("exact_sample", None), ("rounded_6dp_sample", 6)):
        buckets: dict[str, list[str]] = defaultdict(list)
        for idx, feature in enumerate(feature_cols):
            values = sample_x[:, idx].astype(np.float64, copy=False)
            if decimals is not None:
                values = np.round(values, decimals=decimals)
            values = np.nan_to_num(values, nan=9.87654321e123, posinf=8.7654321e123, neginf=-8.7654321e123)
            digest = hashlib.sha1(values.tobytes()).hexdigest()
            buckets[digest].append(feature)
        for digest, features in buckets.items():
            if len(features) > 1:
                rows.append(
                    {
                        "group_kind": kind,
                        "group_hash": digest[:16],
                        "features": features,
                        "feature_count": len(features),
                    }
                )
    if not rows:
        return pl.DataFrame({"group_kind": [], "group_hash": [], "features": [], "feature_count": []})
    return pl.DataFrame(rows)


def _quality_issues(
    feature_quality: pl.DataFrame,
    target_quality: pl.DataFrame,
    correlations: pl.DataFrame,
    duplicate_groups: pl.DataFrame,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for row in feature_quality.filter(pl.col("null_count") > 0).select(["feature", "null_count"]).to_dicts():
        issues.append(_issue("critical", "feature", "feature_null_values", f"{row['feature']} null_count={row['null_count']}"))
    for row in feature_quality.filter(pl.col("nonfinite_count") > 0).select(["feature", "nonfinite_count"]).to_dicts():
        issues.append(_issue("critical", "feature", "feature_nonfinite_values", f"{row['feature']} nonfinite_count={row['nonfinite_count']}"))
    for row in feature_quality.filter(pl.col("constant")).select(["feature"]).head(50).to_dicts():
        issues.append(_issue("warning", "feature", "constant_feature", row["feature"]))
    near_count = feature_quality.filter(pl.col("near_constant")).height
    if near_count:
        issues.append(_issue("warning", "feature", "near_constant_feature_count", str(near_count)))
    extreme_count = feature_quality.filter(pl.col("extreme_abs_ge_1e6")).height
    if extreme_count:
        issues.append(_issue("warning", "feature", "extreme_feature_scale_count", str(extreme_count)))
    for row in target_quality.to_dicts():
        for key in ("valid_null_count", "invalid_nonnull_count", "nonfinite_count", "negative_count", "bad_norm_count"):
            if int(row[key]) > 0:
                issues.append(_issue("critical", "target", key, f"{row['target_col']} {key}={row[key]}"))
        if row.get("target_p99") is not None and float(row["target_p99"]) >= 50.0:
            issues.append(_issue("warning", "target", "large_target_p99", f"{row['target_col']} p99={row['target_p99']:.4f}"))
        if row.get("target_max") is not None and float(row["target_max"]) >= 100.0:
            issues.append(_issue("warning", "target", "large_target_max", f"{row['target_col']} max={row['target_max']:.4f}"))
    if not duplicate_groups.is_empty():
        issues.append(_issue("warning", "feature", "duplicate_or_near_duplicate_feature_groups", str(duplicate_groups.height)))
    high_corr = correlations.filter(pl.col("abs_pearson").fill_null(0.0) >= 0.995).height
    if high_corr:
        issues.append(_issue("warning", "relationship", "very_high_feature_target_correlation_count", str(high_corr)))
    return issues


def _leakage_name_issues(feature_cols: list[str]) -> list[dict[str, Any]]:
    return [
        _issue("critical", "feature", "suspicious_leakage_feature_name", f"{item['feature']} pattern={item['pattern']}")
        for item in detect_leakage_feature_names(feature_cols)
    ]


def _issue(severity: str, category: str, check: str, detail: str, *, batch_id: int | None = None) -> dict[str, Any]:
    return {
        "severity": severity,
        "category": category,
        "check": check,
        "detail": detail,
        "batch_id": batch_id,
    }


def _empty_issues_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "severity": pl.Series([], dtype=pl.Utf8),
            "category": pl.Series([], dtype=pl.Utf8),
            "check": pl.Series([], dtype=pl.Utf8),
            "detail": pl.Series([], dtype=pl.Utf8),
            "batch_id": pl.Series([], dtype=pl.Int64),
        }
    )


def _status_from_issues(issues: pl.DataFrame) -> str:
    if issues.is_empty():
        return "PASS"
    severities = set(issues["severity"].to_list())
    if "critical" in severities:
        return "FAIL"
    return "PASS_WITH_WARNINGS"


def _read_batch_index(path: Path | None) -> dict[int, int]:
    if path is None:
        return {}
    df = pl.read_parquet(path)
    if "stage1_available_pos" not in df.columns:
        return {}
    return {
        int(row["batch_id"]): int(row["stage1_available_pos"])
        for row in df.select(["batch_id", "stage1_available_pos"]).to_dicts()
    }


def _batch_segment(batch_id: int, batch_index: dict[int, int], segments: int) -> int:
    if segments <= 1:
        return 0
    if not batch_index:
        return 0
    max_pos = max(batch_index.values())
    if max_pos <= 0:
        return 0
    pos = batch_index.get(int(batch_id), 0)
    return min(segments - 1, int(pos * segments / (max_pos + 1)))


def _feature_columns_from_first_batch(features_dir: Path) -> list[str]:
    first = next(iter(sorted(features_dir.glob("batch_*.parquet"))), None)
    if first is None:
        raise FileNotFoundError(f"No feature batches found in {features_dir}")
    df = pl.read_parquet(first, n_rows=1)
    return [col for col in df.columns if col not in {"timestamp", "batch_id"} and not col.startswith("target_")]


def _batch_id_from_path(path: Path) -> int | None:
    stem = path.stem
    if not stem.startswith("batch_"):
        return None
    try:
        return int(stem.removeprefix("batch_"))
    except ValueError:
        return None


def _feature_asset_role(feature: str) -> str:
    if feature.startswith("T_") and "__" in feature:
        return feature.split("__", 1)[0]
    if feature.startswith("C_") and "__" in feature:
        return feature.split("__", 1)[0]
    return "unprefixed"


def _feature_family(feature: str) -> str:
    base = feature.split("__", 1)[-1]
    return base.split("_", 1)[0] if "_" in base else base


def _root_slug(root_key: str) -> str:
    return root_key.lower().replace("/", "_")


def _finite_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _default_report_path(
    project_root: Path,
    *,
    target_asset: str,
    root_key: str,
    regression_variant: str,
) -> Path:
    today = datetime.now(timezone.utc).date().isoformat()
    report_dir = project_root / "docs" / "research"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / (
        f"stage1-feature-target-quality-audit-"
        f"{_root_slug(root_key).replace('_', '-')}-"
        f"{normalize_htf_asset_id(target_asset).lower()}-"
        f"{regression_variant}-{today}.md"
    )


def _write_markdown_report(
    report_path: Path,
    *,
    summary: dict[str, Any],
    manifest: dict[str, Any],
    issues: pl.DataFrame,
    feature_quality: pl.DataFrame,
    target_quality: pl.DataFrame,
    correlations: pl.DataFrame,
    duplicate_groups: pl.DataFrame,
    output_dir: Path,
) -> None:
    top_feature_issues = _top_rows(feature_quality.filter((pl.col("null_count") > 0) | (pl.col("nonfinite_count") > 0)), 20)
    top_corr = _top_rows(correlations, 20)
    constant_count = feature_quality.filter(pl.col("constant")).height
    near_constant_count = feature_quality.filter(pl.col("near_constant")).height
    prefix_counts = Counter(feature_quality["asset_role"].to_list())
    family_counts = Counter(feature_quality["feature_family"].to_list())
    lines = [
        "# Stage-1 Feature And Regression Target Quality Audit",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Status: **{summary['status']}**",
        "",
        "## Scope",
        "",
        f"- Asset/root: `{summary['target_asset']} {summary['root']}`",
        f"- Regression variant: `{summary['regression_variant']}`",
        f"- Merged target column: `{summary['merged_target_col']}`",
        f"- Feature rows seen: {summary['feature_rows_seen']:,}",
        f"- Feature columns: {summary['feature_columns_count']:,}",
        f"- Source manifest: `{summary['manifest_path']}`",
        f"- Machine outputs: `{output_dir}`",
        "",
        "## Important Target-Scale Warning",
        "",
        "`distance_vol_v1` is arithmetically validated, but it normalizes a multi-hour future distance by a short-horizon volatility denominator. Large values can therefore be valid arithmetic while still being a poor modeling scale. This audit does not create or promote a corrected target.",
        "",
        "## Manifest Snapshot",
        "",
        f"- Manifest output rows: {manifest.get('output_rows')}",
        f"- Manifest batches: {manifest.get('stage1_batch_index_rows')}",
        f"- Manifest duplicate count: {manifest.get('duplicate_count')}",
        f"- Manifest null feature count: {manifest.get('null_feature_count')}",
        "",
        "## Issues",
        "",
    ]
    if issues.is_empty():
        lines.append("No issues recorded.")
    else:
        lines.extend(["| Severity | Category | Check | Detail |", "|---|---|---|---|"])
        for row in issues.sort(["severity", "category", "check"]).to_dicts():
            lines.append(f"| {row['severity']} | {row['category']} | `{row['check']}` | {row['detail']} |")
    lines.extend(
        [
            "",
            "## Target Summary",
            "",
            "| Target | Valid Rows | p50 | p95 | p99 | p999 | Max | Raw p99 | Vol p50 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in target_quality.to_dicts():
        lines.append(
            f"| `{row['target_col']}` | {row['valid_rows']:,} | "
            f"{_fmt(row['target_p50'])} | {_fmt(row['target_p95'])} | "
            f"{_fmt(row['target_p99'])} | {_fmt(row['target_p999'])} | "
            f"{_fmt(row['target_max'])} | {_fmt(row['raw_pct_p99'])} | "
            f"{_fmt(row['vol_pct_p50'])} |"
        )
    lines.extend(
        [
            "",
            "## Feature Summary",
            "",
            f"- Constant features: {constant_count}",
            f"- Near-constant features: {near_constant_count}",
            f"- Duplicate/near-duplicate sample groups: {duplicate_groups.height}",
            f"- Asset-role counts: `{dict(prefix_counts)}`",
            f"- Top feature families: `{dict(family_counts.most_common(12))}`",
            "",
            "Top feature quality issues:",
            "",
        ]
    )
    if not top_feature_issues:
        lines.append("- None")
    for row in top_feature_issues:
        lines.append(
            f"- `{row['feature']}` null={row['null_count']} "
            f"nonfinite={row['nonfinite_count']} max_abs={_fmt(row['max_abs'])}"
        )
    lines.extend(["", "## Top Feature-Target Correlations", "", "| Target | Feature | Pearson | Spearman sample | n |", "|---|---|---:|---:|---:|"])
    for row in top_corr:
        lines.append(
            f"| `{row['target_col']}` | `{row['feature']}` | "
            f"{_fmt(row['pearson'])} | {_fmt(row['spearman_sample'])} | {row['pearson_n']} |"
        )
    lines.extend(
        [
            "",
            "## Output Tables",
            "",
            "- `feature_quality.parquet`",
            "- `target_quality.parquet`",
            "- `feature_target_correlations.parquet`",
            "- `correlation_stability.parquet`",
            "- `duplicate_feature_groups.parquet`",
            "- `issues.parquet`",
            "- `audit_summary.json`",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n")


def _top_rows(df: pl.DataFrame, n: int) -> list[dict[str, Any]]:
    if df.is_empty():
        return []
    if "abs_pearson" in df.columns:
        return df.sort("abs_pearson", descending=True).head(n).to_dicts()
    return df.head(n).to_dicts()


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(value) or math.isinf(value):
        return "-"
    return f"{value:.6g}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only quality audit for Stage-1 merged features and regression targets."
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--target-asset", default="BTCUSDT")
    parser.add_argument("--context-assets", default="core-ex-target")
    parser.add_argument("--root", default="8h/B", choices=sorted(STAGE1_MULTIASSET_ROOT_LAYOUTS))
    parser.add_argument("--regression-variant", default=REGRESSION_VARIANT)
    parser.add_argument("--merged-target-col", default=UP_EXTREME_COL, choices=TARGET_COLS)
    parser.add_argument("--multiasset-dataset-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=None)
    parser.add_argument("--sample-rows", type=int, default=20_000)
    parser.add_argument("--stability-segments", type=int, default=5)
    parser.add_argument("--write-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    target_asset = normalize_htf_asset_id(args.target_asset)
    context_assets = parse_stage1_context_assets(args.context_assets, target_asset=target_asset)
    result = run_quality_audit(
        project_root=Path(args.project_root),
        target_asset=target_asset,
        context_assets=context_assets,
        root_key=str(args.root),
        regression_variant=str(args.regression_variant),
        merged_target_col=str(args.merged_target_col),
        multiasset_dataset_dir=args.multiasset_dataset_dir,
        output_dir=args.output_dir,
        report_path=args.report_path,
        write_report=bool(args.write_report),
        sample_rows=int(args.sample_rows),
        stability_segments=int(args.stability_segments),
    )
    print(
        f"{result.status} {target_asset} {args.root}: "
        f"rows={result.summary['feature_rows_seen']:,} "
        f"features={result.summary['feature_columns_count']:,} "
        f"issues={result.issues.height} output={result.output_dir}"
    )
    if result.report_path:
        print(f"Report: {result.report_path}")
    return 0 if result.status != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
