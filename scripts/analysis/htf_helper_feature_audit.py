from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from scripts.project_paths import ensure_project_root_on_path  # noqa: E402

PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))

from scripts.htf_backtest.catboost.utils import get_feature_columns  # noqa: E402
DEFAULT_MERGED_ROOT = (
    PROJECT_ROOT
    / "test_output"
    / "htf_walkforward_diagnostics"
    / "20260411_153744_merged"
)
DEFAULT_OUTPUT_BASE = PROJECT_ROOT / "test_output" / "htf_helper_feature_audit"

ROOT_CONFIGS = {
    "8h/B": {
        "slug": "8h_b",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers" / "1m" / "target_4class",
        "eval_batches": 500,
    },
    "8h/C": {
        "slug": "8h_c",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_shift4h" / "1m" / "target_4class",
        "eval_batches": 500,
    },
    "24h/B": {
        "slug": "24h_b",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_24h" / "1m" / "target_4class",
        "eval_batches": 500,
    },
    "24h/C": {
        "slug": "24h_c",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_24h_shift12h" / "1m" / "target_4class",
        "eval_batches": 500,
    },
    "7d/B": {
        "slug": "7d_b",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_7d" / "1m" / "target_4class",
        "eval_batches": 170,
    },
    "7d/C": {
        "slug": "7d_c",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_7d_shift84h" / "1m" / "target_4class",
        "eval_batches": 170,
    },
}


def _helper_kind(name: str) -> str:
    if any(
        token in name
        for token in (
            "phi",
            "kappa",
            "halflife",
            "persistence",
            "asymmetry",
            "regime",
            "is_stationary",
        )
    ):
        return "parameter_or_discrete"
    return "dynamic_continuous"


def _read_eval_feature_frame(features_dir: Path, eval_batches: int) -> pl.DataFrame:
    files = sorted(features_dir.glob("batch_*.parquet"))
    if not files:
        raise FileNotFoundError(f"No feature batches found in {features_dir}")
    selected_files = files[-eval_batches:]
    helper_cols = [c for c in pl.read_parquet(selected_files[0]).columns if c.startswith("H_")]
    frames = [pl.read_parquet(path, columns=["timestamp", *helper_cols]) for path in selected_files]
    return pl.concat(frames, how="vertical_relaxed")


def _per_feature_stats(eval_df: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for feature in [c for c in eval_df.columns if c.startswith("H_")]:
        series = eval_df[feature]
        non_null = series.drop_nulls()
        n_rows = len(series)
        n_non_null = len(non_null)
        rows.append(
            {
                "feature": feature,
                "null_rate": float(series.null_count() / max(1, n_rows)),
                "n_unique": int(non_null.n_unique()) if n_non_null else 0,
                "std": float(non_null.std() or 0.0) if n_non_null else 0.0,
                "zero_frac": float((non_null == 0).mean()) if n_non_null else 1.0,
                "min": float(non_null.min() or 0.0) if n_non_null else None,
                "max": float(non_null.max() or 0.0) if n_non_null else None,
                "helper_kind": _helper_kind(feature),
                "degenerate_constant": bool(n_non_null > 0 and non_null.n_unique() <= 1),
                "near_constant": bool(n_non_null > 0 and float(non_null.std() or 0.0) < 1e-6),
            }
        )
    return pl.DataFrame(rows)


def build_audit(merged_root: Path) -> dict[str, pl.DataFrame]:
    root_summary_rows: list[dict[str, object]] = []
    detail_frames: list[pl.DataFrame] = []

    for root, cfg in ROOT_CONFIGS.items():
        slug = str(cfg["slug"])
        features_dir = Path(cfg["features_dir"])
        eval_df = _read_eval_feature_frame(features_dir, int(cfg["eval_batches"]))

        sample_batch = pl.read_parquet(sorted(features_dir.glob("batch_*.parquet"))[-1])
        model_feature_cols = get_feature_columns(sample_batch)
        helper_model_cols = [c for c in model_feature_cols if c.startswith("H_")]

        stability = pl.read_parquet(
            merged_root
            / "step2"
            / "root_topk"
            / "PredictionValuesChange"
            / slug
            / "feature_importance_stability.parquet"
        )
        helper_stability = (
            stability.filter(pl.col("feature").str.starts_with("H_"))
            .select(["feature", "selected_step_freq", "mean_importance"])
        )

        detail = (
            _per_feature_stats(eval_df)
            .join(helper_stability, on="feature", how="left")
            .with_columns(
                [
                    pl.lit(root).alias("root"),
                    pl.lit(slug).alias("root_slug"),
                ]
            )
        )
        detail_frames.append(detail)

        root_summary_rows.append(
            {
                "root": root,
                "root_slug": slug,
                "eval_rows": int(eval_df.height),
                "helper_cols_saved": int(len([c for c in eval_df.columns if c.startswith("H_")])),
                "helper_cols_in_model": int(len(helper_model_cols)),
                "helper_max_null_rate": float(detail["null_rate"].max() or 0.0) if not detail.is_empty() else None,
                "helper_constant_count": int(detail["degenerate_constant"].sum()) if not detail.is_empty() else 0,
                "helper_near_constant_count": int(detail["near_constant"].sum()) if not detail.is_empty() else 0,
                "helpers_selected_over_10pct": int(
                    detail.filter(pl.col("selected_step_freq") > 0.10).height
                ),
                "helpers_selected_over_20pct": int(
                    detail.filter(pl.col("selected_step_freq") > 0.20).height
                ),
                "helper_mean_selected_step_freq": float(detail["selected_step_freq"].mean() or 0.0)
                if not detail.is_empty()
                else None,
                "helper_mean_importance": float(detail["mean_importance"].mean() or 0.0)
                if not detail.is_empty()
                else None,
            }
        )

    detail_df = pl.concat(detail_frames, how="diagonal_relaxed")
    root_summary = pl.DataFrame(root_summary_rows).sort("root")
    degenerate = detail_df.filter(pl.col("degenerate_constant") | pl.col("near_constant")).sort(
        ["root", "degenerate_constant", "std", "n_unique"],
        descending=[False, True, False, False],
    )
    selected = detail_df.filter(pl.col("selected_step_freq") > 0.10).sort(
        ["root", "selected_step_freq", "mean_importance"],
        descending=[False, True, True],
    )
    helper_kind_summary = (
        detail_df.group_by(["root", "helper_kind"])
        .agg(
            [
                pl.len().alias("n_features"),
                pl.col("selected_step_freq").mean().alias("mean_selected_step_freq"),
                pl.col("mean_importance").mean().alias("mean_importance"),
                pl.col("degenerate_constant").sum().alias("constant_count"),
                pl.col("near_constant").sum().alias("near_constant_count"),
            ]
        )
        .sort(["root", "mean_selected_step_freq"], descending=[False, True])
    )

    return {
        "root_summary": root_summary,
        "helper_feature_detail": detail_df.sort(["root", "selected_step_freq"], descending=[False, True]),
        "degenerate_helpers": degenerate,
        "selected_helpers": selected,
        "helper_kind_summary": helper_kind_summary,
    }


def write_outputs(output_root: Path, frames: dict[str, pl.DataFrame], merged_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.write_csv(output_root / f"{name}.csv")
        frame.write_parquet(output_root / f"{name}.parquet")

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "merged_root": str(merged_root),
        "output_root": str(output_root),
        "rows": {name: int(frame.height) for name, frame in frames.items()},
    }
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-root", type=Path, default=DEFAULT_MERGED_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_BASE)
    args = parser.parse_args()

    merged_root = args.merged_root.expanduser().resolve()
    frames = build_audit(merged_root)
    output_root = args.output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    write_outputs(output_root, frames, merged_root)
    print(output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
