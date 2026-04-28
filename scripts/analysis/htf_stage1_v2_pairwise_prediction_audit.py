from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "data" / "htf_backtest_results"
DEFAULT_TEST_OUTPUT = PROJECT_ROOT / "test_output"

SELECTED_PREDICTION_FILE = "stage1_v2_pred_batch_predictions_selected.parquet"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build pairwise relationship and conflict-resolution artifacts from "
            "Stage-1-v2 persisted selected prediction rows."
        )
    )
    parser.add_argument(
        "--run-id",
        type=str,
        help="Run id under data/htf_backtest_results/.",
    )
    parser.add_argument(
        "--run-path",
        type=str,
        help="Absolute or relative path to a Stage-1-v2 run directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional output directory. Defaults under test_output/.",
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
    return DEFAULT_TEST_OUTPUT / f"stage1_v2_pairwise_prediction_audit_{run_dir.name}"


def _batch_sort_key(path: Path) -> tuple[int, str]:
    try:
        batch_token = path.parent.parent.name
        batch_num = int(batch_token.split("_", 1)[1])
    except Exception:
        batch_num = -1
    return batch_num, str(path)


def _discover_prediction_paths(run_dir: Path) -> list[Path]:
    paths = sorted(
        run_dir.glob(f"catboost/*/*/batch_*/stage1_v2/{SELECTED_PREDICTION_FILE}"),
        key=_batch_sort_key,
    )
    if not paths:
        raise SystemExit(f"No selected prediction files found under: {run_dir}")
    return paths


def _load_selected_predictions(paths: Iterable[Path]) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for path in paths:
        df = pl.read_parquet(
            path,
            columns=["pred_batch", "timestamp", "action_key", "y_true", "y_pred"],
        )
        if df.is_empty():
            continue
        frames.append(
            df.with_columns(
                [
                    (pl.col("y_true") >= 2).cast(pl.Int8).alias("true_dir"),
                    (pl.col("y_pred") >= 2).cast(pl.Int8).alias("pred_dir"),
                    (pl.col("y_true") == pl.col("y_pred")).cast(pl.Int8).alias(
                        "class_correct"
                    ),
                    ((pl.col("y_true") >= 2) == (pl.col("y_pred") >= 2))
                    .cast(pl.Int8)
                    .alias("dir_correct"),
                ]
            )
        )
    if not frames:
        raise SystemExit("Selected prediction files were discovered, but all were empty.")
    return pl.concat(frames, how="vertical_relaxed").sort(
        ["pred_batch", "timestamp", "action_key"]
    )


def _safe_rate(mask: np.ndarray) -> float | None:
    if mask.size == 0:
        return None
    return float(np.mean(mask))


def _safe_corr(x: np.ndarray, y: np.ndarray) -> float | None:
    if x.size == 0 or y.size == 0:
        return None
    if np.allclose(x, x[0]) or np.allclose(y, y[0]):
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _bucket_from_same_dir_count(same_dir_count: int) -> str:
    if same_dir_count <= 1:
        return "isolated_0_1"
    if same_dir_count <= 3:
        return "minority_2_3"
    if same_dir_count <= 5:
        return "majority_4_5"
    return "consensus_6_7"


def _pivot_predictions(long_df: pl.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pdf = long_df.to_pandas()
    base = (
        pdf[["pred_batch", "timestamp", "y_true", "true_dir"]]
        .drop_duplicates(subset=["pred_batch", "timestamp"])
        .sort_values(["pred_batch", "timestamp"])
        .set_index(["pred_batch", "timestamp"])
    )
    wide_pred = pdf.pivot(
        index=["pred_batch", "timestamp"],
        columns="action_key",
        values="y_pred",
    ).sort_index()
    wide_pred_dir = pdf.pivot(
        index=["pred_batch", "timestamp"],
        columns="action_key",
        values="pred_dir",
    ).sort_index()
    wide_class_ok = pdf.pivot(
        index=["pred_batch", "timestamp"],
        columns="action_key",
        values="class_correct",
    ).sort_index()
    wide_dir_ok = pdf.pivot(
        index=["pred_batch", "timestamp"],
        columns="action_key",
        values="dir_correct",
    ).sort_index()
    return base, wide_pred, wide_pred_dir, wide_class_ok, wide_dir_ok


def _build_pairwise_relationships(
    wide_pred: pd.DataFrame,
    wide_pred_dir: pd.DataFrame,
    wide_class_ok: pd.DataFrame,
    wide_dir_ok: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    combos = list(wide_pred.columns)
    pair_rows: list[dict[str, object]] = []
    agreement_matrix = pd.DataFrame(1.0, index=combos, columns=combos)
    conflict_edge_matrix = pd.DataFrame(0.0, index=combos, columns=combos)
    class_agreement_matrix = pd.DataFrame(1.0, index=combos, columns=combos)

    for idx, combo_a in enumerate(combos):
        pred_a = wide_pred[combo_a].to_numpy(dtype=np.int16, copy=False)
        dir_a = wide_pred_dir[combo_a].to_numpy(dtype=np.int8, copy=False)
        class_ok_a = wide_class_ok[combo_a].to_numpy(dtype=np.int8, copy=False).astype(bool)
        dir_ok_a = wide_dir_ok[combo_a].to_numpy(dtype=np.int8, copy=False).astype(bool)
        for combo_b in combos[idx + 1 :]:
            pred_b = wide_pred[combo_b].to_numpy(dtype=np.int16, copy=False)
            dir_b = wide_pred_dir[combo_b].to_numpy(dtype=np.int8, copy=False)
            class_ok_b = (
                wide_class_ok[combo_b].to_numpy(dtype=np.int8, copy=False).astype(bool)
            )
            dir_ok_b = wide_dir_ok[combo_b].to_numpy(dtype=np.int8, copy=False).astype(bool)

            class_agree = pred_a == pred_b
            dir_agree = dir_a == dir_b
            conflict = ~dir_agree

            conflict_rows = int(conflict.sum())
            conflict_dir_acc_a = _safe_rate(dir_ok_a[conflict])
            conflict_dir_acc_b = _safe_rate(dir_ok_b[conflict])
            conflict_class_acc_a = _safe_rate(class_ok_a[conflict])
            conflict_class_acc_b = _safe_rate(class_ok_b[conflict])
            conflict_dir_edge_a_minus_b = (
                None
                if conflict_dir_acc_a is None or conflict_dir_acc_b is None
                else float(conflict_dir_acc_a - conflict_dir_acc_b)
            )
            conflict_class_edge_a_minus_b = (
                None
                if conflict_class_acc_a is None or conflict_class_acc_b is None
                else float(conflict_class_acc_a - conflict_class_acc_b)
            )

            a_up_b_down = conflict & (dir_a == 1)
            a_down_b_up = conflict & (dir_a == 0)

            row = {
                "combo_a": combo_a,
                "combo_b": combo_b,
                "n_rows": int(pred_a.size),
                "class_agreement_rate": float(np.mean(class_agree)),
                "direction_agreement_rate": float(np.mean(dir_agree)),
                "opposite_direction_rate": float(np.mean(conflict)),
                "both_class_correct_rate": float(np.mean(class_ok_a & class_ok_b)),
                "both_direction_correct_rate": float(np.mean(dir_ok_a & dir_ok_b)),
                "both_direction_wrong_rate": float(
                    np.mean((~dir_ok_a) & (~dir_ok_b))
                ),
                "conflict_rows": conflict_rows,
                "conflict_rate": float(np.mean(conflict)),
                "conflict_dir_acc_a": conflict_dir_acc_a,
                "conflict_dir_acc_b": conflict_dir_acc_b,
                "conflict_class_acc_a": conflict_class_acc_a,
                "conflict_class_acc_b": conflict_class_acc_b,
                "conflict_dir_edge_a_minus_b": conflict_dir_edge_a_minus_b,
                "conflict_class_edge_a_minus_b": conflict_class_edge_a_minus_b,
                "a_up_b_down_rows": int(a_up_b_down.sum()),
                "a_up_b_down_dir_acc_a": _safe_rate(dir_ok_a[a_up_b_down]),
                "a_up_b_down_dir_acc_b": _safe_rate(dir_ok_b[a_up_b_down]),
                "a_down_b_up_rows": int(a_down_b_up.sum()),
                "a_down_b_up_dir_acc_a": _safe_rate(dir_ok_a[a_down_b_up]),
                "a_down_b_up_dir_acc_b": _safe_rate(dir_ok_b[a_down_b_up]),
            }
            pair_rows.append(row)

            agreement_matrix.loc[combo_a, combo_b] = row["direction_agreement_rate"]
            agreement_matrix.loc[combo_b, combo_a] = row["direction_agreement_rate"]
            class_agreement_matrix.loc[combo_a, combo_b] = row["class_agreement_rate"]
            class_agreement_matrix.loc[combo_b, combo_a] = row["class_agreement_rate"]
            conflict_edge_matrix.loc[combo_a, combo_b] = (
                conflict_dir_edge_a_minus_b or 0.0
            )
            conflict_edge_matrix.loc[combo_b, combo_a] = (
                -(conflict_dir_edge_a_minus_b or 0.0)
            )

    pairwise_df = pd.DataFrame(pair_rows).sort_values(
        ["direction_agreement_rate", "conflict_dir_edge_a_minus_b"],
        ascending=[False, False],
    )
    return pairwise_df, agreement_matrix, class_agreement_matrix, conflict_edge_matrix


def _build_conflict_advantage_summary(pairwise_df: pd.DataFrame) -> pd.DataFrame:
    combo_rows: list[dict[str, object]] = []
    combos = sorted(set(pairwise_df["combo_a"]).union(pairwise_df["combo_b"]))
    for combo in combos:
        edges: list[float] = []
        weights: list[int] = []
        agreement_rates: list[float] = []
        for row in pairwise_df.itertuples(index=False):
            if row.combo_a == combo:
                edge = row.conflict_dir_edge_a_minus_b
                weight = row.conflict_rows
                agreement_rates.append(row.direction_agreement_rate)
            elif row.combo_b == combo:
                edge = (
                    None
                    if row.conflict_dir_edge_a_minus_b is None
                    else -float(row.conflict_dir_edge_a_minus_b)
                )
                weight = row.conflict_rows
                agreement_rates.append(row.direction_agreement_rate)
            else:
                continue
            if edge is not None and weight > 0:
                edges.append(float(edge))
                weights.append(int(weight))
        weighted_edge = None
        if edges and weights and sum(weights) > 0:
            weighted_edge = float(np.average(np.asarray(edges), weights=np.asarray(weights)))
        combo_rows.append(
            {
                "action_key": combo,
                "pair_count": int(len(agreement_rates)),
                "mean_direction_agreement_rate": (
                    float(np.mean(agreement_rates)) if agreement_rates else None
                ),
                "mean_conflict_dir_edge_vs_others": (
                    float(np.mean(edges)) if edges else None
                ),
                "weighted_conflict_dir_edge_vs_others": weighted_edge,
            }
        )
    return pd.DataFrame(combo_rows).sort_values(
        "weighted_conflict_dir_edge_vs_others",
        ascending=False,
        na_position="last",
    )


def _build_peer_support_artifacts(
    base: pd.DataFrame,
    wide_pred: pd.DataFrame,
    wide_pred_dir: pd.DataFrame,
    wide_class_ok: pd.DataFrame,
    wide_dir_ok: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    combos = list(wide_pred.columns)
    peer_support_rows: list[dict[str, object]] = []
    per_step_rows: list[dict[str, object]] = []

    pred_batch_index = base.index.get_level_values("pred_batch").to_numpy(dtype=np.int32)

    for combo in combos:
        pred_combo = wide_pred[combo].to_numpy(dtype=np.int16, copy=False)
        dir_combo = wide_pred_dir[combo].to_numpy(dtype=np.int8, copy=False)
        class_ok_combo = (
            wide_class_ok[combo].to_numpy(dtype=np.int8, copy=False).astype(bool)
        )
        dir_ok_combo = wide_dir_ok[combo].to_numpy(dtype=np.int8, copy=False).astype(bool)

        same_dir_count = np.zeros_like(dir_combo, dtype=np.int16)
        same_class_count = np.zeros_like(pred_combo, dtype=np.int16)
        for other in combos:
            if other == combo:
                continue
            same_dir_count += (
                wide_pred_dir[other].to_numpy(dtype=np.int8, copy=False) == dir_combo
            ).astype(np.int16)
            same_class_count += (
                wide_pred[other].to_numpy(dtype=np.int16, copy=False) == pred_combo
            ).astype(np.int16)

        for idx in range(pred_combo.size):
            peer_support_rows.append(
                {
                    "action_key": combo,
                    "pred_batch": int(pred_batch_index[idx]),
                    "peer_same_direction_count": int(same_dir_count[idx]),
                    "peer_same_direction_rate": float(same_dir_count[idx] / (len(combos) - 1)),
                    "peer_same_class_count": int(same_class_count[idx]),
                    "peer_same_class_rate": float(same_class_count[idx] / (len(combos) - 1)),
                    "support_bucket": _bucket_from_same_dir_count(int(same_dir_count[idx])),
                    "direction_correct": int(dir_ok_combo[idx]),
                    "class_correct": int(class_ok_combo[idx]),
                }
            )

        per_step = (
            pd.DataFrame(
                {
                    "pred_batch": pred_batch_index,
                    "peer_same_direction_rate": same_dir_count / float(len(combos) - 1),
                    "peer_same_class_rate": same_class_count / float(len(combos) - 1),
                    "direction_correct": dir_ok_combo.astype(np.int8),
                    "class_correct": class_ok_combo.astype(np.int8),
                }
            )
            .groupby("pred_batch", as_index=False)
            .agg(
                mean_peer_same_direction_rate=("peer_same_direction_rate", "mean"),
                mean_peer_same_class_rate=("peer_same_class_rate", "mean"),
                step_direction_accuracy=("direction_correct", "mean"),
                step_class_accuracy=("class_correct", "mean"),
            )
        )
        per_step["action_key"] = combo
        per_step_rows.extend(per_step.to_dict(orient="records"))

    peer_support_df = pd.DataFrame(peer_support_rows).sort_values(
        ["action_key", "pred_batch"]
    )
    support_bucket_summary = (
        peer_support_df.groupby(["action_key", "support_bucket"], as_index=False)
        .agg(
            n_rows=("direction_correct", "size"),
            direction_accuracy=("direction_correct", "mean"),
            class_accuracy=("class_correct", "mean"),
            mean_peer_same_direction_rate=("peer_same_direction_rate", "mean"),
            mean_peer_same_class_rate=("peer_same_class_rate", "mean"),
        )
        .sort_values(["action_key", "support_bucket"])
    )

    per_step_df = pd.DataFrame(per_step_rows).sort_values(["action_key", "pred_batch"])
    support_corr_rows: list[dict[str, object]] = []
    for combo, grp in per_step_df.groupby("action_key", sort=True):
        x_dir = grp["mean_peer_same_direction_rate"].to_numpy(dtype=np.float64, copy=False)
        x_class = grp["mean_peer_same_class_rate"].to_numpy(dtype=np.float64, copy=False)
        y_dir = grp["step_direction_accuracy"].to_numpy(dtype=np.float64, copy=False)
        y_class = grp["step_class_accuracy"].to_numpy(dtype=np.float64, copy=False)

        majority_mask = x_dir >= (4.0 / 7.0)
        minority_mask = x_dir <= (3.0 / 7.0)
        majority_dir_acc = _safe_rate(y_dir[majority_mask])
        minority_dir_acc = _safe_rate(y_dir[minority_mask])
        support_corr_rows.append(
            {
                "action_key": combo,
                "steps": int(len(grp)),
                "corr_support_vs_step_direction_accuracy": _safe_corr(x_dir, y_dir),
                "corr_support_vs_step_class_accuracy": _safe_corr(x_dir, y_class),
                "corr_class_support_vs_step_direction_accuracy": _safe_corr(x_class, y_dir),
                "majority_supported_steps": int(np.sum(majority_mask)),
                "minority_or_split_steps": int(np.sum(minority_mask)),
                "majority_supported_dir_accuracy": majority_dir_acc,
                "minority_or_split_dir_accuracy": minority_dir_acc,
                "majority_supported_dir_accuracy_lift": (
                    None
                    if majority_dir_acc is None or minority_dir_acc is None
                    else float(majority_dir_acc - minority_dir_acc)
                ),
            }
        )
    support_corr_df = pd.DataFrame(support_corr_rows).sort_values(
        "corr_support_vs_step_direction_accuracy",
        ascending=False,
        na_position="last",
    )
    return support_bucket_summary, per_step_df, support_corr_df


def _write_table(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    if parquet_path is not None:
        pl.from_pandas(df).write_parquet(parquet_path)


def _main() -> int:
    args = _parse_args()
    run_dir = _resolve_run_dir(args)
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else _default_output_dir(run_dir).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    prediction_paths = _discover_prediction_paths(run_dir)
    long_df = _load_selected_predictions(prediction_paths)
    base, wide_pred, wide_pred_dir, wide_class_ok, wide_dir_ok = _pivot_predictions(long_df)

    pairwise_df, direction_agreement_matrix, class_agreement_matrix, conflict_edge_matrix = (
        _build_pairwise_relationships(
            wide_pred=wide_pred,
            wide_pred_dir=wide_pred_dir,
            wide_class_ok=wide_class_ok,
            wide_dir_ok=wide_dir_ok,
        )
    )
    conflict_advantage_df = _build_conflict_advantage_summary(pairwise_df)
    support_bucket_df, per_step_support_df, support_corr_df = _build_peer_support_artifacts(
        base=base,
        wide_pred=wide_pred,
        wide_pred_dir=wide_pred_dir,
        wide_class_ok=wide_class_ok,
        wide_dir_ok=wide_dir_ok,
    )

    _write_table(
        pairwise_df,
        output_dir / "pairwise_prediction_relationships.csv",
        output_dir / "pairwise_prediction_relationships.parquet",
    )
    direction_agreement_matrix.to_csv(output_dir / "direction_agreement_matrix.csv")
    class_agreement_matrix.to_csv(output_dir / "class_agreement_matrix.csv")
    conflict_edge_matrix.to_csv(output_dir / "conflict_direction_edge_matrix.csv")
    _write_table(
        conflict_advantage_df,
        output_dir / "per_combo_conflict_advantage.csv",
        output_dir / "per_combo_conflict_advantage.parquet",
    )
    _write_table(
        support_bucket_df,
        output_dir / "per_combo_support_bucket_summary.csv",
        output_dir / "per_combo_support_bucket_summary.parquet",
    )
    _write_table(
        per_step_support_df,
        output_dir / "per_combo_step_support_summary.csv",
        output_dir / "per_combo_step_support_summary.parquet",
    )
    _write_table(
        support_corr_df,
        output_dir / "per_combo_support_correlation.csv",
        output_dir / "per_combo_support_correlation.parquet",
    )

    summary = {
        "run_id": run_dir.name,
        "run_path": str(run_dir),
        "step_count": int(base.index.get_level_values("pred_batch").nunique()),
        "row_count": int(len(base)),
        "combo_count": int(len(wide_pred.columns)),
        "pair_count": int(len(pairwise_df)),
        "mean_direction_agreement_rate": float(pairwise_df["direction_agreement_rate"].mean()),
        "mean_class_agreement_rate": float(pairwise_df["class_agreement_rate"].mean()),
        "mean_opposite_direction_rate": float(pairwise_df["opposite_direction_rate"].mean()),
        "top_direction_agreement_pairs": pairwise_df.nlargest(
            5, "direction_agreement_rate"
        )[
            [
                "combo_a",
                "combo_b",
                "direction_agreement_rate",
                "class_agreement_rate",
                "conflict_dir_edge_a_minus_b",
            ]
        ].to_dict(orient="records"),
        "lowest_direction_agreement_pairs": pairwise_df.nsmallest(
            5, "direction_agreement_rate"
        )[
            [
                "combo_a",
                "combo_b",
                "direction_agreement_rate",
                "class_agreement_rate",
                "conflict_dir_edge_a_minus_b",
            ]
        ].to_dict(orient="records"),
        "conflict_advantage_leaders": conflict_advantage_df.head(5).to_dict(
            orient="records"
        ),
        "support_predictiveness_leaders": support_corr_df.head(5).to_dict(
            orient="records"
        ),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print(f"\nArtifacts written to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
