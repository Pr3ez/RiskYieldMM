from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from scripts.htf_backtest.catboost.utils import get_feature_columns


PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
TARGET = "target_4class"
TF = "1m"


@dataclass(frozen=True)
class RootConfig:
    root: str
    features_dir: Path
    labels_dir: Path
    complete_batch_start: int


ROOTS: tuple[RootConfig, ...] = (
    RootConfig(
        root="8h/B",
        features_dir=PROJECT_ROOT / "data" / "htf_with_helpers",
        labels_dir=PROJECT_ROOT / "data" / "htf_4class_labels",
        complete_batch_start=43,
    ),
    RootConfig(
        root="8h/C",
        features_dir=PROJECT_ROOT / "data" / "htf_with_helpers_shift4h",
        labels_dir=PROJECT_ROOT / "data" / "htf_4class_labels_shift4h",
        complete_batch_start=43,
    ),
    RootConfig(
        root="24h/B",
        features_dir=PROJECT_ROOT / "data" / "htf_with_helpers_24h",
        labels_dir=PROJECT_ROOT / "data" / "htf_4class_labels_24h",
        complete_batch_start=15,
    ),
    RootConfig(
        root="24h/C",
        features_dir=PROJECT_ROOT / "data" / "htf_with_helpers_24h_shift12h",
        labels_dir=PROJECT_ROOT / "data" / "htf_4class_labels_24h_shift12h",
        complete_batch_start=15,
    ),
    RootConfig(
        root="7d/B",
        features_dir=PROJECT_ROOT / "data" / "htf_with_helpers_7d",
        labels_dir=PROJECT_ROOT / "data" / "htf_4class_labels_7d",
        complete_batch_start=4,
    ),
    RootConfig(
        root="7d/C",
        features_dir=PROJECT_ROOT / "data" / "htf_with_helpers_7d_shift84h",
        labels_dir=PROJECT_ROOT / "data" / "htf_4class_labels_7d_shift84h",
        complete_batch_start=4,
    ),
)


def _batch_paths(root: RootConfig) -> list[Path]:
    batch_dir = root.features_dir / TF / TARGET
    return sorted(batch_dir.glob("batch_*.parquet"))


def _prepare_frame(features_path: Path, labels_path: Path) -> pl.DataFrame:
    # Read a single batch only. This keeps the audit bounded to one parquet
    # at a time and avoids the OOM path seen in earlier whole-root scans.
    features = pl.read_parquet(features_path)
    labels = pl.read_parquet(labels_path, columns=["timestamp", "batch_id", TARGET])
    valid_keys = labels.filter(pl.col(TARGET) >= 0).select(["timestamp", "batch_id"])
    return features.join(valid_keys, on=["timestamp", "batch_id"], how="inner")


def _scan_root(root: RootConfig) -> dict:
    batch_paths = _batch_paths(root)
    if not batch_paths:
        raise FileNotFoundError(f"No batch parquet files found for {root.root}")

    feature_cols: list[str] | None = None
    null_counts: dict[str, int] = {}
    value_counts: dict[str, dict[str, int]] = {}
    row_count = 0
    batch_count = 0
    scanned_batches: list[int] = []

    for path in batch_paths:
        batch_idx = int(path.stem.split("_")[1])
        if batch_idx < root.complete_batch_start:
            continue

        labels_path = root.labels_dir / TF / f"batch_{batch_idx:04d}.parquet"
        if not labels_path.exists():
            raise FileNotFoundError(f"Missing label batch for {root.root}: {labels_path}")

        frame = _prepare_frame(path, labels_path)
        if frame.height == 0:
            continue

        if feature_cols is None:
            feature_cols = get_feature_columns(frame, target_col=TARGET)
            null_counts = {col: 0 for col in feature_cols}
            value_counts = {col: {} for col in feature_cols}

        # Only keep model-visible columns plus batch_id for lightweight stats.
        slim = frame.select(["batch_id", *feature_cols])
        row_count += slim.height
        batch_count += 1
        scanned_batches.append(batch_idx)

        for col in feature_cols:
            series = slim.get_column(col)
            null_counts[col] += int(series.null_count())

            non_null = series.drop_nulls()
            if non_null.is_empty():
                continue

            # Track the number of times distinct values appear across batches.
            # This is enough to detect globally constant features without
            # materializing full-root columns in memory.
            vc = non_null.value_counts(sort=False)
            counts = value_counts[col]
            values = vc.get_column(col).to_list()
            freqs = vc.get_column("count").to_list()
            for value, freq in zip(values, freqs, strict=True):
                key = json.dumps(value, sort_keys=True, default=str)
                counts[key] = counts.get(key, 0) + int(freq)
                if len(counts) > 1:
                    # Once a feature is known non-constant, stop growing the map.
                    # Keep only two exemplars to cap memory.
                    if len(counts) > 2:
                        first_two = dict(list(counts.items())[:2])
                        value_counts[col] = first_two
                        counts = first_two

    if feature_cols is None:
        raise RuntimeError(f"No valid complete batches found for {root.root}")

    constant_features = sorted(
        col
        for col, counts in value_counts.items()
        if row_count > 0 and len(counts) == 1 and null_counts[col] == 0
    )
    null_features = sorted(col for col, count in null_counts.items() if count > 0)

    return {
        "root": root.root,
        "features_dir": str(root.features_dir / TF / TARGET),
        "labels_dir": str(root.labels_dir / TF),
        "complete_batch_start": root.complete_batch_start,
        "scanned_batch_count": batch_count,
        "first_scanned_batch": scanned_batches[0] if scanned_batches else None,
        "last_scanned_batch": scanned_batches[-1] if scanned_batches else None,
        "row_count": row_count,
        "feature_count": len(feature_cols),
        "null_feature_count": len(null_features),
        "constant_feature_count": len(constant_features),
        "null_features": null_features,
        "constant_features": constant_features,
        "null_counts": {col: null_counts[col] for col in null_features},
    }


def main() -> int:
    started_at = datetime.now(timezone.utc)
    results = [_scan_root(root) for root in ROOTS]
    union_null = sorted({col for result in results for col in result["null_features"]})
    union_constant = sorted(
        {col for result in results for col in result["constant_features"]}
    )

    payload = {
        "generated_at": started_at.isoformat(),
        "target": TARGET,
        "timeframe": TF,
        "roots": [
            {
                "root": root.root,
                "features_dir": str(root.features_dir),
                "labels_dir": str(root.labels_dir),
                "complete_batch_start": root.complete_batch_start,
            }
            for root in ROOTS
        ],
        "results": results,
        "union_null_features": union_null,
        "union_constant_features": union_constant,
        "union_null_feature_count": len(union_null),
        "union_constant_feature_count": len(union_constant),
    }

    output_dir = (
        PROJECT_ROOT / "test_output" / "htf_feature_null_constant_audit"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{stamp}_complete_batches_only_audit.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
