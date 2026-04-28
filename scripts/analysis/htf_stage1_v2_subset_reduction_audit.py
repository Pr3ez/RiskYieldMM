from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path

import pandas as pd
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "data" / "htf_backtest_results"
DEFAULT_TEST_OUTPUT = PROJECT_ROOT / "test_output"
COMBO_METRICS_FILE = "stage1_v2_combo_metrics.parquet"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Exhaustively evaluate fixed combo subsets on Stage-1-v2 fixed-policy "
            "step metrics using a chronological train/test split."
        )
    )
    parser.add_argument("--run-id", type=str, help="Run id under data/htf_backtest_results/.")
    parser.add_argument("--run-path", type=str, help="Absolute or relative run directory path.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional explicit output directory. Defaults under test_output/.",
    )
    parser.add_argument(
        "--train-frac",
        type=float,
        default=0.70,
        help="Chronological train fraction used to select the subset.",
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=1,
        help="Minimum subset size to evaluate.",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=None,
        help="Maximum subset size to evaluate. Default: full pool size.",
    )
    return parser.parse_args()


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    if bool(args.run_id) == bool(args.run_path):
        raise SystemExit("Exactly one of --run-id or --run-path must be provided.")
    if args.run_id:
        run_dir = RESULTS_ROOT / str(args.run_id)
    else:
        candidate = Path(str(args.run_path))
        run_dir = candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate)
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory not found: {run_dir}")
    return run_dir


def _default_output_dir(run_dir: Path) -> Path:
    return DEFAULT_TEST_OUTPUT / f"stage1_v2_subset_reduction_audit_{run_dir.name}"


def _batch_sort_key(path: Path) -> tuple[int, str]:
    try:
        batch_token = path.parent.parent.name
        batch_num = int(batch_token.split("_", 1)[1])
    except Exception:
        batch_num = -1
    return batch_num, str(path)


def _discover_metric_paths(run_dir: Path) -> list[Path]:
    paths = sorted(
        run_dir.glob(f"catboost/*/*/batch_*/stage1_v2/{COMBO_METRICS_FILE}"),
        key=_batch_sort_key,
    )
    if not paths:
        raise SystemExit(f"No files named {COMBO_METRICS_FILE} found under: {run_dir}")
    return paths


def _load_step_metrics(run_dir: Path) -> pd.DataFrame:
    paths = _discover_metric_paths(run_dir)
    frames: list[pl.DataFrame] = []
    columns = [
        "pred_batch",
        "action_key",
        "filtered_rank",
        "filtered_accuracy",
        "filtered_cross_direction_error",
        "filtered_macro_f1",
        "n_features_used",
    ]
    for path in paths:
        df = pl.read_parquet(path, columns=columns)
        if not df.is_empty():
            frames.append(df)
    if not frames:
        raise SystemExit("Metric inputs were discovered, but all were empty.")
    pdf = (
        pl.concat(frames, how="vertical_relaxed")
        .sort(["pred_batch", "filtered_rank", "action_key"])
        .to_pandas()
    )
    pdf["direction_accuracy"] = 1.0 - pdf["filtered_cross_direction_error"]
    return pdf


def _train_test_split(pred_batches: list[int], train_frac: float) -> tuple[set[int], set[int]]:
    pred_batches = sorted(pred_batches)
    n_steps = len(pred_batches)
    if n_steps < 2:
        raise SystemExit("Need at least 2 pred batches for a train/test split.")
    split_idx = max(1, min(n_steps - 1, int(math.floor(n_steps * train_frac))))
    train_batches = set(pred_batches[:split_idx])
    test_batches = set(pred_batches[split_idx:])
    return train_batches, test_batches


def _evaluate_subset(df: pd.DataFrame, subset: tuple[str, ...]) -> pd.DataFrame:
    subset_df = df[df["action_key"].isin(subset)].copy()
    chosen = (
        subset_df.sort_values(["pred_batch", "filtered_rank", "action_key"])
        .groupby("pred_batch", as_index=False)
        .head(1)
        .sort_values("pred_batch")
        .reset_index(drop=True)
    )
    return chosen


def _split_metrics(chosen: pd.DataFrame, split_batches: set[int]) -> dict[str, float | int]:
    part = chosen[chosen["pred_batch"].isin(split_batches)].copy()
    if part.empty:
        return {
            "steps": 0,
            "mean_dir_acc": float("nan"),
            "mean_acc": float("nan"),
            "mean_macro_f1": float("nan"),
            "mean_rank": float("nan"),
            "global_top1_capture_rate": float("nan"),
            "global_top2_capture_rate": float("nan"),
        }
    return {
        "steps": int(len(part)),
        "mean_dir_acc": float(part["direction_accuracy"].mean()),
        "mean_acc": float(part["filtered_accuracy"].mean()),
        "mean_macro_f1": float(part["filtered_macro_f1"].mean()),
        "mean_rank": float(part["filtered_rank"].mean()),
        "global_top1_capture_rate": float((part["filtered_rank"] == 1).mean()),
        "global_top2_capture_rate": float((part["filtered_rank"] <= 2).mean()),
    }


def _subset_rows(df: pd.DataFrame, train_batches: set[int], test_batches: set[int]) -> pd.DataFrame:
    combos = sorted(df["action_key"].unique().tolist())
    rows: list[dict[str, object]] = []
    for k in range(1, len(combos) + 1):
        for subset in itertools.combinations(combos, k):
            chosen = _evaluate_subset(df, subset)
            train_metrics = _split_metrics(chosen, train_batches)
            test_metrics = _split_metrics(chosen, test_batches)
            rows.append(
                {
                    "subset_size": k,
                    "subset_key": ",".join(subset),
                    "subset_list": list(subset),
                    "train_steps": train_metrics["steps"],
                    "train_mean_dir_acc": train_metrics["mean_dir_acc"],
                    "train_mean_acc": train_metrics["mean_acc"],
                    "train_mean_macro_f1": train_metrics["mean_macro_f1"],
                    "train_mean_rank": train_metrics["mean_rank"],
                    "train_global_top1_capture_rate": train_metrics["global_top1_capture_rate"],
                    "train_global_top2_capture_rate": train_metrics["global_top2_capture_rate"],
                    "test_steps": test_metrics["steps"],
                    "test_mean_dir_acc": test_metrics["mean_dir_acc"],
                    "test_mean_acc": test_metrics["mean_acc"],
                    "test_mean_macro_f1": test_metrics["mean_macro_f1"],
                    "test_mean_rank": test_metrics["mean_rank"],
                    "test_global_top1_capture_rate": test_metrics["global_top1_capture_rate"],
                    "test_global_top2_capture_rate": test_metrics["global_top2_capture_rate"],
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["subset_size", "train_mean_dir_acc", "test_mean_dir_acc"],
        ascending=[True, False, False],
    )


def _best_by_size(subset_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.Series] = []
    for subset_size, grp in subset_df.groupby("subset_size", sort=True):
        best = grp.sort_values(
            ["train_mean_dir_acc", "test_mean_dir_acc", "test_mean_acc"],
            ascending=[False, False, False],
        ).head(1)
        rows.append(best.iloc[0])
    return pd.DataFrame(rows).reset_index(drop=True)


def _write_df(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    if parquet_path is not None:
        pl.from_pandas(df).write_parquet(parquet_path)


def main() -> int:
    args = _parse_args()
    run_dir = _resolve_run_dir(args)
    output_dir = (
        Path(args.output_dir).resolve() if args.output_dir else _default_output_dir(run_dir).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    step_metrics_df = _load_step_metrics(run_dir)
    combos = sorted(step_metrics_df["action_key"].unique().tolist())
    min_size = max(1, int(args.min_size))
    max_size = len(combos) if args.max_size is None else min(len(combos), int(args.max_size))
    if min_size > max_size:
        raise SystemExit("min_size must be <= max_size")

    pred_batches = sorted(step_metrics_df["pred_batch"].unique().tolist())
    train_batches, test_batches = _train_test_split(pred_batches, float(args.train_frac))

    subset_df = _subset_rows(step_metrics_df, train_batches, test_batches)
    subset_df = subset_df[
        (subset_df["subset_size"] >= min_size) & (subset_df["subset_size"] <= max_size)
    ].copy()

    full_pool_row = subset_df[subset_df["subset_size"] == len(combos)].iloc[0]
    subset_df["test_dir_acc_gap_vs_full_pool"] = (
        subset_df["test_mean_dir_acc"] - float(full_pool_row["test_mean_dir_acc"])
    )
    subset_df["test_acc_gap_vs_full_pool"] = (
        subset_df["test_mean_acc"] - float(full_pool_row["test_mean_acc"])
    )
    subset_df["test_top1_capture_gap_vs_full_pool"] = (
        subset_df["test_global_top1_capture_rate"] - float(full_pool_row["test_global_top1_capture_rate"])
    )

    best_size_df = _best_by_size(subset_df)
    best_size_df["test_dir_acc_gap_vs_full_pool"] = (
        best_size_df["test_mean_dir_acc"] - float(full_pool_row["test_mean_dir_acc"])
    )
    best_size_df["test_acc_gap_vs_full_pool"] = (
        best_size_df["test_mean_acc"] - float(full_pool_row["test_mean_acc"])
    )
    best_size_df["test_top1_capture_gap_vs_full_pool"] = (
        best_size_df["test_global_top1_capture_rate"]
        - float(full_pool_row["test_global_top1_capture_rate"])
    )

    summary = {
        "run_id": run_dir.name,
        "run_path": str(run_dir),
        "combo_count": int(len(combos)),
        "step_count": int(len(pred_batches)),
        "train_step_count": int(len(train_batches)),
        "test_step_count": int(len(test_batches)),
        "full_pool": {
            "subset_key": str(full_pool_row["subset_key"]),
            "test_mean_dir_acc": float(full_pool_row["test_mean_dir_acc"]),
            "test_mean_acc": float(full_pool_row["test_mean_acc"]),
            "test_global_top1_capture_rate": float(full_pool_row["test_global_top1_capture_rate"]),
        },
        "best_by_size": best_size_df[
            [
                "subset_size",
                "subset_key",
                "train_mean_dir_acc",
                "test_mean_dir_acc",
                "test_mean_acc",
                "test_global_top1_capture_rate",
                "test_dir_acc_gap_vs_full_pool",
                "test_acc_gap_vs_full_pool",
                "test_top1_capture_gap_vs_full_pool",
            ]
        ].to_dict(orient="records"),
    }

    _write_df(
        subset_df,
        output_dir / "all_subset_metrics.csv",
        output_dir / "all_subset_metrics.parquet",
    )
    _write_df(
        best_size_df,
        output_dir / "best_subset_per_size.csv",
        output_dir / "best_subset_per_size.parquet",
    )
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print(f"\nArtifacts written to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
