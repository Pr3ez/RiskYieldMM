#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.feature_engineering.htf_helper_cache import prepare_raw_features_for_helpers
from scripts.target_models.helpers.cusum import create_cusum_helper
from scripts.target_models.helpers.egarch import create_egarch_helper
from scripts.target_models.helpers.garch import create_garch_helper
from scripts.target_models.helpers.kalman import create_kalman_helper
from scripts.target_models.helpers.ou import create_ou_helper


REQUIRED_COLS = ["timestamp", "open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class HelperSpec:
    name: str
    create: Callable[[], object]


HELPER_SPECS = [
    HelperSpec("ou", lambda: create_ou_helper("4class", 1)),
    HelperSpec("garch", lambda: create_garch_helper("4class", 1)),
    HelperSpec("egarch", lambda: create_egarch_helper("4class", 1)),
    HelperSpec("cusum", lambda: create_cusum_helper("4class", 1)),
    HelperSpec("kalman", lambda: create_kalman_helper("4class", 1)),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit helper causal/live reproducibility.")
    parser.add_argument(
        "--batch-dir",
        type=Path,
        default=Path("data/htf_features/1m"),
        help="Batch directory with OHLCV columns.",
    )
    parser.add_argument(
        "--train-rows",
        type=int,
        default=20000,
        help="Number of rows used to fit helpers.",
    )
    parser.add_argument(
        "--chunk-rows",
        type=int,
        default=256,
        help="Prediction chunk length used for the audit.",
    )
    parser.add_argument(
        "--context-rows",
        type=int,
        default=500,
        help="Historical context rows prepended for chunk-boundary stability check.",
    )
    parser.add_argument(
        "--tol",
        type=float,
        default=1e-8,
        help="Absolute tolerance for drift/causality comparisons.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("test_output/htf_helper_causality_audit"),
        help="Output directory root.",
    )
    return parser.parse_args()


def list_batch_paths(batch_dir: Path) -> list[Path]:
    return sorted(
        path for path in batch_dir.glob("batch_*.parquet") if path.is_file()
    )


def load_rows(batch_dir: Path, required_rows: int) -> pl.DataFrame:
    batch_paths = list_batch_paths(batch_dir)
    if not batch_paths:
        raise FileNotFoundError(f"No batch parquet files found in {batch_dir}")

    frames: list[pl.DataFrame] = []
    rows = 0
    for path in batch_paths:
        df = pl.read_parquet(path).select([c for c in REQUIRED_COLS if c in pl.read_parquet_schema(path).names()])
        missing = [c for c in REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"{path} missing required columns: {missing}")
        frames.append(df)
        rows += len(df)
        if rows >= required_rows:
            break

    if rows < required_rows:
        raise ValueError(
            f"Insufficient rows in {batch_dir}: needed {required_rows}, found {rows}"
        )

    full = pl.concat(frames, how="vertical")
    full = full.sort("timestamp")
    return full.head(required_rows)


def run_prefix_transform(helper, chunk_x: np.ndarray) -> pd.DataFrame:
    rows: list[np.ndarray] = []
    feature_names: list[str] | None = None
    for end in range(1, len(chunk_x) + 1):
        out = helper.transform(chunk_x[:end])
        if feature_names is None:
            feature_names = out.feature_names
        rows.append(out.features.iloc[-1].to_numpy(dtype=float))
    return pd.DataFrame(rows, columns=feature_names)


def diff_frame(lhs: pd.DataFrame, rhs: pd.DataFrame) -> pd.DataFrame:
    lhs_arr = lhs.to_numpy(dtype=float)
    rhs_arr = rhs.to_numpy(dtype=float)
    return pd.DataFrame(np.abs(lhs_arr - rhs_arr), columns=lhs.columns)


def summarize_diff(
    helper_name: str,
    diff_df: pd.DataFrame,
    tol: float,
    check_name: str,
) -> pd.DataFrame:
    rows = []
    for col in diff_df.columns:
        series = diff_df[col].to_numpy(dtype=float)
        diff_mask = np.isfinite(series) & (series > tol)
        first_idx = int(np.argmax(diff_mask)) if diff_mask.any() else -1
        rows.append(
            {
                "helper": helper_name,
                "check": check_name,
                "feature": col,
                "max_abs_diff": float(np.nanmax(series)),
                "mean_abs_diff": float(np.nanmean(series)),
                "rows_diff_gt_tol": int(diff_mask.sum()),
                "first_diff_row": None if first_idx < 0 else first_idx,
                "passes": bool(not diff_mask.any()),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    args = parse_args()
    required_rows = args.train_rows + args.chunk_rows
    context_required_rows = required_rows + args.context_rows
    raw_df = load_rows(args.batch_dir, context_required_rows)
    helper_df = raw_df.select(REQUIRED_COLS[1:])
    x_all, feature_cols = prepare_raw_features_for_helpers(helper_df)

    train_x = x_all[: args.train_rows]
    chunk_x = x_all[args.train_rows : args.train_rows + args.chunk_rows]
    context_x = x_all[args.train_rows - args.context_rows : args.train_rows + args.chunk_rows]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = args.output_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict] = []
    prefix_rows: list[pd.DataFrame] = []
    context_rows: list[pd.DataFrame] = []
    state_rows: list[pd.DataFrame] = []

    for spec in HELPER_SPECS:
        helper = spec.create()
        helper.fit(train_x)

        batch_out = helper.transform(chunk_x).features.reset_index(drop=True)
        prefix_out = run_prefix_transform(helper, chunk_x)
        prefix_diff = diff_frame(batch_out, prefix_out)
        prefix_summary = summarize_diff(spec.name, prefix_diff, args.tol, "prefix_only")

        context_summary = None
        context_out = None
        context_diff = None
        if spec.name not in {"kalman", "egarch"}:
            context_out_full = helper.transform(context_x).features.reset_index(drop=True)
            context_out = context_out_full.tail(args.chunk_rows).reset_index(drop=True)
            context_diff = diff_frame(batch_out, context_out)
            context_summary = summarize_diff(spec.name, context_diff, args.tol, "with_context")

        state_summary = None
        if spec.name in {"kalman", "egarch"} and hasattr(helper, "transform_with_stream_state"):
            split = max(1, args.chunk_rows // 2)
            initial_state = helper.get_state()
            first_out, mid_state = helper.transform_with_stream_state(
                chunk_x[:split], initial_state
            )
            second_out, _ = helper.transform_with_stream_state(chunk_x[split:], mid_state)
            handoff_out = pd.concat(
                [
                    first_out.features.reset_index(drop=True),
                    second_out.features.reset_index(drop=True),
                ],
                ignore_index=True,
            )
            state_diff = diff_frame(batch_out, handoff_out)
            state_summary = summarize_diff(spec.name, state_diff, args.tol, "state_handoff")
            state_rows.append(state_summary)

        prefix_rows.append(prefix_summary)
        if context_summary is not None:
            context_rows.append(context_summary)

        summary_rows.append(
            {
                "helper": spec.name,
                "n_features": len(batch_out.columns),
                "prefix_all_pass": bool(prefix_summary["passes"].all()),
                "prefix_fail_features": int((~prefix_summary["passes"]).sum()),
                "prefix_max_abs_diff": float(prefix_summary["max_abs_diff"].max()),
                "context_all_pass": (
                    None if context_summary is None else bool(context_summary["passes"].all())
                ),
                "context_fail_features": (
                    None if context_summary is None else int((~context_summary["passes"]).sum())
                ),
                "context_max_abs_diff": (
                    None if context_summary is None else float(context_summary["max_abs_diff"].max())
                ),
                "state_handoff_all_pass": (
                    None if state_summary is None else bool(state_summary["passes"].all())
                ),
                "state_handoff_fail_features": (
                    None if state_summary is None else int((~state_summary["passes"]).sum())
                ),
                "state_handoff_max_abs_diff": (
                    None if state_summary is None else float(state_summary["max_abs_diff"].max())
                ),
            }
        )

        helper_dir = out_dir / spec.name
        helper_dir.mkdir(parents=True, exist_ok=True)
        batch_out.to_parquet(helper_dir / "batch_transform.parquet", index=False)
        prefix_out.to_parquet(helper_dir / "prefix_transform_last_rows.parquet", index=False)
        prefix_diff.to_parquet(helper_dir / "prefix_diff.parquet", index=False)
        prefix_summary.to_parquet(helper_dir / "prefix_summary.parquet", index=False)
        if context_summary is not None and context_out is not None and context_diff is not None:
            context_out.to_parquet(helper_dir / "context_transform_tail.parquet", index=False)
            context_diff.to_parquet(helper_dir / "context_diff.parquet", index=False)
            context_summary.to_parquet(helper_dir / "context_summary.parquet", index=False)
        if state_summary is not None:
            handoff_out.to_parquet(helper_dir / "state_handoff_transform.parquet", index=False)
            state_diff.to_parquet(helper_dir / "state_handoff_diff.parquet", index=False)
            state_summary.to_parquet(helper_dir / "state_handoff_summary.parquet", index=False)

    summary_df = pd.DataFrame(summary_rows).sort_values("helper").reset_index(drop=True)
    prefix_df = pd.concat(prefix_rows, ignore_index=True).sort_values(["helper", "feature"])
    context_df = (
        pd.concat(context_rows, ignore_index=True).sort_values(["helper", "feature"])
        if context_rows
        else pd.DataFrame()
    )
    state_df = (
        pd.concat(state_rows, ignore_index=True).sort_values(["helper", "feature"])
        if state_rows
        else pd.DataFrame()
    )

    summary_df.to_csv(out_dir / "helper_overall_summary.csv", index=False)
    summary_df.to_parquet(out_dir / "helper_overall_summary.parquet", index=False)
    prefix_df.to_csv(out_dir / "prefix_summary.csv", index=False)
    prefix_df.to_parquet(out_dir / "prefix_summary.parquet", index=False)
    if len(context_df) > 0:
        context_df.to_csv(out_dir / "context_summary.csv", index=False)
        context_df.to_parquet(out_dir / "context_summary.parquet", index=False)
    if len(state_df) > 0:
        state_df.to_csv(out_dir / "state_handoff_summary.csv", index=False)
        state_df.to_parquet(out_dir / "state_handoff_summary.parquet", index=False)

    meta = {
        "run_id": run_id,
        "batch_dir": str(args.batch_dir),
        "train_rows": args.train_rows,
        "chunk_rows": args.chunk_rows,
        "context_rows": args.context_rows,
        "tol": args.tol,
        "feature_cols": feature_cols,
    }
    (out_dir / "summary.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({"out_dir": str(out_dir), "helpers": len(HELPER_SPECS)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
