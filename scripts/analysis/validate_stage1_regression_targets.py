from __future__ import annotations

import argparse
import json
import sys
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
    RAW_DISTANCE_COLS,
    REGRESSION_VARIANT,
    normalize_variant,
    target_cols_for_variant,
    variant_spec,
)
from scripts.analysis.materialize_stage1_target_variants import (  # noqa: E402
    ROOT_BACKTEST_DIRS,
    parse_roots,
)
from scripts.feature_engineering.htf_asset_registry import normalize_htf_asset_id  # noqa: E402
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (  # noqa: E402
    STAGE1_MULTIASSET_ROOT_LAYOUTS,
    parse_stage1_target_assets,
)
from scripts.project_paths import ensure_project_root_on_path  # noqa: E402


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))


@dataclass(frozen=True)
class ValidationSummary:
    asset_id: str
    root_key: str
    variant: str
    label_dir: Path
    window_path: Path
    counters: dict[str, Any]
    raw_recompute: dict[str, dict[str, Any]]
    window_metadata: dict[str, Any]
    status: str


def validate_regression_target_root(
    *,
    project_root: Path,
    asset_id: str,
    root_key: str,
    variant: str = REGRESSION_VARIANT,
) -> ValidationSummary:
    spec = variant_spec(normalize_variant(variant))
    asset_id = normalize_htf_asset_id(asset_id)
    layout = STAGE1_MULTIASSET_ROOT_LAYOUTS[root_key]
    _, window_backtest_root = ROOT_BACKTEST_DIRS[root_key]
    asset_root = project_root / "data" / "htf_multiasset" / asset_id.lower()
    label_dir = asset_root / f"{layout.label_root}_{spec.label_suffix}" / "1m"
    window_path = asset_root / window_backtest_root / "15m_HTF_combined.parquet"
    paths = sorted(label_dir.glob("batch_*.parquet"))
    if not paths:
        raise FileNotFoundError(f"No regression target batches found in {label_dir}")
    if not window_path.exists():
        raise FileNotFoundError(f"Opposite-family 15m window file not found: {window_path}")

    counters = _validate_basic_invariants([str(path) for path in paths], variant=spec.variant)
    window_metadata = _validate_window_metadata([str(path) for path in paths], window_path, variant=spec.variant)
    raw_recompute = _validate_raw_distances([str(path) for path in paths], window_path, variant=spec.variant)
    problem_count = _problem_count(counters, window_metadata, raw_recompute)
    status = "PASS" if problem_count == 0 else "FAIL"
    return ValidationSummary(
        asset_id=asset_id,
        root_key=root_key,
        variant=spec.variant,
        label_dir=label_dir,
        window_path=window_path,
        counters=counters,
        raw_recompute=raw_recompute,
        window_metadata=window_metadata,
        status=status,
    )


def _validate_basic_invariants(paths: list[str], *, variant: str) -> dict[str, Any]:
    spec = variant_spec(variant)
    lf = pl.scan_parquet(paths)
    valid = spec.valid_col
    reason = spec.reason_col
    vol = "tb_volatility_pct"
    denom = spec.horizon_vol_col or vol
    future = spec.future_bars_col
    maxoff, maxts, minoff, mints = spec.extreme_metadata_cols
    up, upm, dm, dx = spec.target_cols
    raw_up, raw_upm, raw_dm, raw_dx = spec.raw_distance_cols
    result = lf.select(
        pl.len().alias("rows"),
        pl.struct(["timestamp", "batch_id"]).n_unique().alias("unique_ts_batch"),
        pl.col(valid).sum().alias("valid_rows"),
        (~pl.col(valid)).sum().alias("invalid_rows"),
        ((pl.col(valid)) & (~pl.col("is_label_half"))).sum().alias("valid_not_label_half"),
        ((pl.col(valid)) & (pl.col(reason) != "ok")).sum().alias("valid_reason_not_ok"),
        ((~pl.col(valid)) & (pl.col(reason) == "ok")).sum().alias("invalid_reason_ok"),
        (
            (pl.col(valid))
            & (
                pl.col(vol).is_null()
                | (~pl.col(vol).is_finite())
                | (pl.col(vol) <= 0)
            )
        ).sum().alias("valid_bad_vol"),
        ((pl.col(valid)) & (pl.col(future) <= 0)).sum().alias("valid_bad_future_bars"),
        (
            (pl.col(valid))
            & (
                (pl.col(maxoff) < 0)
                | (pl.col(maxoff) >= pl.col(future))
                | (pl.col(minoff) < 0)
                | (pl.col(minoff) >= pl.col(future))
            )
        ).sum().alias("valid_bad_offsets"),
        ((pl.col(valid)) & (pl.col(maxts).is_null() | pl.col(mints).is_null())).sum().alias("valid_null_extreme_ts"),
        ((pl.col(valid)) & ((pl.col(up) < pl.col(upm)) | (pl.col(dx) < pl.col(dm)))).sum().alias("extreme_less_than_mean"),
        (
            (pl.col(valid))
            & ((pl.col(up) < 0) | (pl.col(upm) < 0) | (pl.col(dm) < 0) | (pl.col(dx) < 0))
        ).sum().alias("negative_targets"),
        (
            (pl.col(valid))
            & (~(pl.col(up).is_finite() & pl.col(upm).is_finite() & pl.col(dm).is_finite() & pl.col(dx).is_finite()))
        ).sum().alias("nonfinite_targets"),
        (
            (~pl.col(valid))
            & (pl.col(up).is_not_null() | pl.col(upm).is_not_null() | pl.col(dm).is_not_null() | pl.col(dx).is_not_null())
        ).sum().alias("invalid_nonnull_targets"),
        (
            (~pl.col(valid))
            & (
                pl.col(raw_up).is_not_null()
                | pl.col(raw_upm).is_not_null()
                | pl.col(raw_dm).is_not_null()
                | pl.col(raw_dx).is_not_null()
            )
        ).sum().alias("invalid_nonnull_raw"),
        ((pl.col(spec.variant_col) != spec.variant)).sum().alias("bad_variant"),
        ((pl.col(spec.policy_col) != "opposite_family_first_half")).sum().alias("bad_policy"),
        *[
            (
                (pl.col(valid))
                & ((pl.col(target) - (pl.col(raw) / pl.col(denom))).abs() > 1e-9)
            ).sum().alias(f"{target}_bad_norm")
            for target, raw in zip(spec.target_cols, spec.raw_distance_cols, strict=True)
        ],
        *(
            [
                (
                    (pl.col(valid))
                    & ((pl.col(spec.horizon_minutes_col) - (pl.col(future) * 15.0)).abs() > 1e-9)
                ).sum().alias("horizon_minutes_mismatch"),
                (
                    (pl.col(valid))
                    & (
                        (
                            pl.col(spec.horizon_vol_col)
                            - (pl.col(vol) * (pl.col(spec.horizon_minutes_col).sqrt()))
                        ).abs()
                        > 1e-9
                    )
                ).sum().alias("horizon_vol_mismatch"),
            ]
            if spec.horizon_minutes_col and spec.horizon_vol_col
            else []
        ),
    ).collect().to_dicts()[0]
    return {key: _json_scalar(value) for key, value in result.items()}


def _validate_window_metadata(paths: list[str], window_path: Path, *, variant: str) -> dict[str, Any]:
    spec = variant_spec(variant)
    stats_df = _window_stats(window_path)
    unique_df = (
        pl.scan_parquet(paths)
        .filter(pl.col(spec.valid_col))
        .select(
            [
                "label_window_batch_id",
                spec.future_bars_col,
                spec.extreme_metadata_cols[0],
                spec.extreme_metadata_cols[1],
                spec.extreme_metadata_cols[2],
                spec.extreme_metadata_cols[3],
            ]
        )
        .unique()
        .collect()
    )
    joined = unique_df.join(stats_df, on="label_window_batch_id", how="left")
    out = joined.select(
        pl.len().alias("unique_label_windows_used"),
        pl.col("expected_future_bars").is_null().sum().alias("missing_window_stats"),
        (pl.col(spec.future_bars_col) != pl.col("expected_future_bars")).sum().alias("future_bars_mismatch"),
        (pl.col(spec.extreme_metadata_cols[0]) != pl.col("expected_max_high_offset")).sum().alias("max_high_offset_mismatch"),
        (pl.col(spec.extreme_metadata_cols[1]) != pl.col("expected_max_high_ts")).sum().alias("max_high_ts_mismatch"),
        (pl.col(spec.extreme_metadata_cols[2]) != pl.col("expected_min_low_offset")).sum().alias("min_low_offset_mismatch"),
        (pl.col(spec.extreme_metadata_cols[3]) != pl.col("expected_min_low_ts")).sum().alias("min_low_ts_mismatch"),
    ).to_dicts()[0]
    out["source_window_count"] = int(stats_df.height)
    return {key: _json_scalar(value) for key, value in out.items()}


def _validate_raw_distances(paths: list[str], window_path: Path, *, variant: str) -> dict[str, dict[str, Any]]:
    spec = variant_spec(variant)
    lookup = _window_lookup(window_path)
    df = (
        pl.scan_parquet(paths)
        .filter(pl.col(spec.valid_col))
        .select(["label_window_batch_id", "close", *spec.raw_distance_cols])
        .collect()
    )
    max_errors = {col: 0.0 for col in spec.raw_distance_cols}
    violations = {col: 0 for col in spec.raw_distance_cols}
    rows_checked = 0
    for key, part in df.partition_by(
        "label_window_batch_id",
        as_dict=True,
        maintain_order=True,
    ).items():
        batch_id = int(key[0] if isinstance(key, tuple) else key)
        highs, lows = lookup[batch_id]
        close = part["close"].to_numpy().astype("float64")
        up_pct = np.maximum((highs[None, :] - close[:, None]) / close[:, None], 0.0)
        down_pct = np.maximum((close[:, None] - lows[None, :]) / close[:, None], 0.0)
        expected = {
            spec.raw_distance_cols[0]: up_pct.max(axis=1),
            spec.raw_distance_cols[1]: up_pct.mean(axis=1),
            spec.raw_distance_cols[2]: down_pct.mean(axis=1),
            spec.raw_distance_cols[3]: down_pct.max(axis=1),
        }
        rows_checked += len(close)
        for col, exp in expected.items():
            got = part[col].to_numpy().astype("float64")
            err = np.abs(got - exp)
            max_errors[col] = max(max_errors[col], float(np.max(err)))
            violations[col] += int(np.sum(err > 1e-12))
    return {
        col: {
            "rows_checked": int(rows_checked),
            "max_abs_error": float(max_errors[col]),
            "violations_gt_1e_12": int(violations[col]),
        }
        for col in spec.raw_distance_cols
    }


def _window_stats(window_path: Path) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for batch_id, highs, lows, timestamps in _iter_windows(window_path):
        maxoff = int(np.argmax(highs)) if len(highs) else None
        minoff = int(np.argmin(lows)) if len(lows) else None
        rows.append(
            {
                "label_window_batch_id": int(batch_id),
                "expected_future_bars": int(len(highs)),
                "expected_max_high_offset": maxoff,
                "expected_max_high_ts": timestamps[maxoff] if maxoff is not None else None,
                "expected_min_low_offset": minoff,
                "expected_min_low_ts": timestamps[minoff] if minoff is not None else None,
            }
        )
    return pl.DataFrame(rows)


def _window_lookup(window_path: Path) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    return {
        batch_id: (highs, lows)
        for batch_id, highs, lows, _ in _iter_windows(window_path)
    }


def _iter_windows(window_path: Path):
    window = pl.read_parquet(window_path)
    if "is_label_half" in window.columns:
        window = window.filter(pl.col("is_label_half"))
    pos_col = "family_bar_pos" if "family_bar_pos" in window.columns else "timestamp"
    for key, part in window.sort(["batch_id", pos_col]).partition_by(
        "batch_id",
        as_dict=True,
        maintain_order=True,
    ).items():
        batch_id = int(key[0] if isinstance(key, tuple) else key)
        yield (
            batch_id,
            part["high"].to_numpy().astype("float64"),
            part["low"].to_numpy().astype("float64"),
            part["timestamp"].to_list(),
        )


def _problem_count(
    counters: dict[str, Any],
    window_metadata: dict[str, Any],
    raw_recompute: dict[str, dict[str, Any]],
) -> int:
    ignore = {
        "rows",
        "unique_ts_batch",
        "valid_rows",
        "invalid_rows",
        "source_window_count",
        "unique_label_windows_used",
    }
    total = 0
    for key, value in counters.items():
        if key in ignore:
            continue
        total += int(value)
    for key, value in window_metadata.items():
        if key in ignore:
            continue
        total += int(value)
    for metrics in raw_recompute.values():
        total += int(metrics["violations_gt_1e_12"])
    total += 0 if counters["rows"] == counters["unique_ts_batch"] else 1
    return total


def _json_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value


def write_validation_report(
    *,
    project_root: Path,
    summaries: list[ValidationSummary],
) -> Path:
    today = datetime.now(timezone.utc).date().isoformat()
    report_dir = project_root / "docs" / "research"
    report_dir.mkdir(parents=True, exist_ok=True)
    if len(summaries) == 1:
        summary = summaries[0]
        report_path = report_dir / (
            f"reg-distance-target-validation-"
            f"{summary.variant}-"
            f"{summary.root_key.lower().replace('/', '-')}-"
            f"{summary.asset_id.lower()}-{today}.md"
        )
    else:
        variants = "_".join(sorted({summary.variant for summary in summaries}))
        report_path = report_dir / f"reg-distance-target-validation-{variants}-{today}.md"

    lines = [
        "# Volatility-Normalized Distance Target Validation",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Asset | Root | Status | Rows | Valid Rows | Unique Label Windows |",
        "|---|---|---|---:|---:|---:|",
    ]
    for summary in summaries:
        lines.append(
            "| "
            f"{summary.asset_id} | {summary.root_key} | {summary.status} | "
            f"{summary.counters['rows']:,} | {summary.counters['valid_rows']:,} | "
            f"{summary.window_metadata['unique_label_windows_used']:,} |"
        )
    for summary in summaries:
        lines.extend(
            [
                "",
                f"## {summary.asset_id} {summary.root_key}",
                "",
                f"Label root: `{summary.label_dir}`",
                f"Window source: `{summary.window_path}`",
                "",
                "Invariant counters:",
                "",
            ]
        )
        for key, value in summary.counters.items():
            lines.append(f"- `{key}`: {value}")
        lines.extend(["", "Window metadata counters:", ""])
        for key, value in summary.window_metadata.items():
            lines.append(f"- `{key}`: {value}")
        lines.extend(["", "Independent raw-distance recomputation:", ""])
        for col, metrics in summary.raw_recompute.items():
            lines.append(
                f"- `{col}`: rows={metrics['rows_checked']:,}, "
                f"max_abs_error={metrics['max_abs_error']:.3e}, "
                f"violations_gt_1e_12={metrics['violations_gt_1e_12']}"
            )
    report_path.write_text("\n".join(lines) + "\n")
    return report_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate volatility-normalized Stage-1 regression target roots."
    )
    parser.add_argument("--assets", default="BTCUSDT")
    parser.add_argument("--roots", nargs="*", default=["8h/B"])
    parser.add_argument("--variant", default=REGRESSION_VARIANT)
    parser.add_argument("--write-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summaries: list[ValidationSummary] = []
    for asset_id in parse_stage1_target_assets(args.assets):
        for root_key in parse_roots(args.roots):
            summary = validate_regression_target_root(
                project_root=PROJECT_ROOT,
                asset_id=asset_id,
                root_key=root_key,
                variant=args.variant,
            )
            summaries.append(summary)
            print(
                f"{summary.status} {summary.asset_id} {summary.root_key}: "
                f"rows={summary.counters['rows']:,} "
                f"valid={summary.counters['valid_rows']:,} "
                f"windows={summary.window_metadata['unique_label_windows_used']:,}"
            )
    if args.write_report:
        report = write_validation_report(project_root=PROJECT_ROOT, summaries=summaries)
        print(f"Report: {report}")
    return 0 if all(summary.status == "PASS" for summary in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
