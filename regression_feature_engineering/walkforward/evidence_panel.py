"""Build lightweight RPF feature panels from existing diagnostic evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from regression_feature_engineering.walkforward.ablation import FAMILY_PREFIXES, select_ablation_features
from regression_feature_engineering.walkforward.classification.targets import UP_EXTREME, side_from_target
from regression_feature_engineering.walkforward.config import load_clean_config
from regression_feature_engineering.walkforward.data import resolve_context
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_feature_panels"

PANEL_DIRECTION_CORE = "direction_core"
PANEL_BINARY_SELECTED = "binary_selected"
PANEL_HYBRID_DIRECTION_BINARY = "hybrid_direction_binary"
PANEL_WIDTH_CONTEXT = "width_context"
PANEL_KINDS = (
    PANEL_DIRECTION_CORE,
    PANEL_BINARY_SELECTED,
    PANEL_HYBRID_DIRECTION_BINARY,
    PANEL_WIDTH_CONTEXT,
)

DIRECTION_TARGETS = (
    "target_extreme_up_minus_down",
    "target_mean_up_minus_down",
    "target_reg_direction_extreme_up_share_hvol_v2",
    "target_reg_direction_mean_up_share_hvol_v2",
)
WIDTH_TARGETS = (
    "target_extreme_total",
    "target_mean_total",
    "target_reg_distance_up_extreme_hvol_v2",
    "target_reg_distance_down_extreme_hvol_v2",
    "target_reg_distance_up_mean_high_hvol_v2",
    "target_reg_distance_down_mean_low_hvol_v2",
)

KIND_ALLOWED_FAMILIES: dict[str, tuple[str, ...]] = {
    PANEL_DIRECTION_CORE: (
        "acceptance_persistence",
        "interaction_confluence",
        "structural_room",
        "liquidity_volume_pressure",
        "spike_breakout",
        "regime_calendar_state",
    ),
    PANEL_BINARY_SELECTED: (
        "interaction_confluence",
        "structural_room",
        "liquidity_volume_pressure",
        "acceptance_persistence",
        "spike_breakout",
        "regime_calendar_state",
    ),
    PANEL_HYBRID_DIRECTION_BINARY: (
        "acceptance_persistence",
        "interaction_confluence",
        "structural_room",
        "liquidity_volume_pressure",
        "spike_breakout",
        "regime_calendar_state",
        "volatility_state",
        "temporal_memory_transforms",
    ),
    PANEL_WIDTH_CONTEXT: (
        "volatility_state",
        "temporal_memory_transforms",
        "spike_breakout",
        "structural_room",
        "regime_calendar_state",
    ),
}


def main() -> int:
    args = parse_args()
    config = load_clean_config(args.config)
    asset = str(args.asset or config.asset)
    root = str(args.root or config.root)
    target_col = str(args.target_col)
    context = resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=UP_EXTREME)
    feature_universe = select_ablation_features(context.manifest.feature_columns, str(args.feature_ablation))

    evidence = build_evidence_table(
        diagnostics_root=Path(args.diagnostics_root),
        selected_feature_root=Path(args.selected_feature_root),
        manifest_features=feature_universe,
        target_col=target_col,
    )
    panel = select_panel(
        evidence,
        panel_kind=str(args.panel_kind),
        selected_count=int(args.selected_count),
        per_family_limit=int(args.per_family_limit),
        min_score=float(args.min_score),
    )
    if panel.is_empty():
        raise ValueError("Evidence panel selected no features")

    run_root = run_root_for_args(args, target_col)
    run_root.mkdir(parents=True, exist_ok=True)
    evidence.write_parquet(run_root / "evidence_scores.parquet")
    panel.write_parquet(run_root / "selected_panel_features.parquet")

    selected_features = [str(value) for value in panel["feature"].to_list()]
    payload = {
        "schema_version": "rpf_frozen_panel_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset": asset,
        "root": root,
        "root_id": context.root_id,
        "target_col": target_col,
        "feature_set": config.feature_set,
        "target_variant": config.target_variant,
        "feature_ablation": str(args.feature_ablation),
        "selection_algorithm": "diagnostic_evidence_v1",
        "panel_kind": str(args.panel_kind),
        "selected_feature_count": len(selected_features),
        "selected_features": selected_features,
        "selected_count_requested": int(args.selected_count),
        "per_family_limit": int(args.per_family_limit),
        "min_score": float(args.min_score),
        "candidate_feature_count": int(evidence.height),
        "allowed_families": list(KIND_ALLOWED_FAMILIES[str(args.panel_kind)]),
        "notes": (
            "This panel is a research candidate built from prior diagnostics and selected-feature history. "
            "It narrows the candidate universe; it is not a promoted leak-safe final feature set until confirmed "
            "on later held-out walk-forward windows."
        ),
    }
    panel_path = run_root / f"selected_panel_{len(selected_features)}.json"
    panel_path.write_text(json.dumps(payload, indent=2) + "\n")
    (run_root / "selected_panel.md").write_text(panel_markdown(payload, panel))
    print(
        "[rpf-evidence-panel] done "
        f"kind={args.panel_kind} candidates={evidence.height} selected={len(selected_features)} panel={panel_path}",
        flush=True,
    )
    return 0


def build_evidence_table(
    *,
    diagnostics_root: Path,
    selected_feature_root: Path,
    manifest_features: tuple[str, ...],
    target_col: str,
) -> pl.DataFrame:
    manifest_set = set(manifest_features)
    base = pl.DataFrame({"feature": list(manifest_features)}).with_columns(
        pl.col("feature").map_elements(feature_family, return_dtype=pl.String).alias("family")
    )
    side = side_from_target(target_col)
    corr = load_correlation_evidence(diagnostics_root, manifest_set, side=side)
    bins = load_bin_spread_evidence(diagnostics_root, manifest_set, side=side)
    selected = load_binary_selected_evidence(selected_feature_root, manifest_set, target_col)
    evidence = base.join(corr, on="feature", how="left").join(bins, on="feature", how="left").join(
        selected, on="feature", how="left"
    )
    numeric_cols = [
        "direction_abs_spearman",
        "direction_side_spearman",
        "width_abs_spearman",
        "direction_abs_bin_spread",
        "direction_side_bin_spread",
        "width_abs_bin_spread",
        "binary_selected_count",
        "binary_selected_runs",
        "binary_selected_batches",
    ]
    for col in numeric_cols:
        if col not in evidence.columns:
            evidence = evidence.with_columns(pl.lit(0.0).alias(col))
    evidence = evidence.with_columns([pl.col(col).fill_null(0.0) for col in numeric_cols])
    evidence = evidence.with_columns(
        normalized_score_expr("binary_selected_count").alias("binary_selected_score"),
        normalized_score_expr("binary_selected_batches").alias("binary_batch_score"),
        side_token_expr(side).alias("side_token_score"),
        opposite_side_token_expr(side).alias("opposite_side_token_score"),
    )
    return evidence.with_columns(
        (
            2.40 * pl.col("direction_side_spearman")
            + 1.30 * pl.col("direction_side_bin_spread")
            + 1.25 * pl.col("binary_selected_score")
            + 0.75 * pl.col("binary_batch_score")
            + 0.30 * pl.col("direction_abs_spearman")
            + 0.20 * pl.col("direction_abs_bin_spread")
            + 0.35 * pl.col("width_abs_spearman")
            + 0.15 * pl.col("width_abs_bin_spread")
            + 0.40 * pl.col("side_token_score")
            - 0.25 * pl.col("opposite_side_token_score")
        ).alias("hybrid_direction_binary_score"),
        (
            2.80 * pl.col("direction_side_spearman")
            + 1.45 * pl.col("direction_side_bin_spread")
            + 0.35 * pl.col("binary_selected_score")
            + 0.25 * pl.col("direction_abs_spearman")
            + 0.20 * pl.col("width_abs_spearman")
            + 0.35 * pl.col("side_token_score")
            - 0.20 * pl.col("opposite_side_token_score")
        ).alias("direction_core_score"),
        (
            2.00 * pl.col("binary_selected_score")
            + 1.00 * pl.col("binary_batch_score")
            + 0.35 * pl.col("direction_abs_spearman")
            + 0.20 * pl.col("direction_abs_bin_spread")
        ).alias("binary_selected_score_total"),
        (
            2.00 * pl.col("width_abs_spearman")
            + 1.25 * pl.col("width_abs_bin_spread")
            + 0.25 * pl.col("direction_abs_spearman")
        ).alias("width_context_score"),
    )


def load_correlation_evidence(diagnostics_root: Path, manifest_set: set[str], *, side: str) -> pl.DataFrame:
    inventory = diagnostics_root / "rpf_feature_diagnostic_inventory" / "manifest_feature_correlation_best.parquet"
    frames: list[pl.DataFrame] = []
    if inventory.exists():
        frames.append(pl.read_parquet(inventory))
    else:
        for path in diagnostics_root.glob("**/feature_target_correlations.parquet"):
            try:
                frame = pl.read_parquet(path)
            except Exception:
                continue
            if {"feature", "target", "abs_spearman"}.issubset(frame.columns):
                frames.append(frame)
    if not frames:
        return pl.DataFrame({"feature": [], "direction_abs_spearman": [], "direction_side_spearman": [], "width_abs_spearman": []})
    raw = pl.concat(frames, how="vertical_relaxed")
    if "max_abs_spearman" in raw.columns:
        score_expr = pl.col("max_abs_spearman")
    else:
        score_expr = pl.col("abs_spearman")
    if "median_spearman" in raw.columns:
        signed_expr = pl.col("median_spearman")
    elif "mean_spearman" in raw.columns:
        signed_expr = pl.col("mean_spearman")
    elif "spearman" in raw.columns:
        signed_expr = pl.col("spearman")
    else:
        signed_expr = pl.lit(0.0)
    side_signed_expr = signed_expr if side == "up" else -signed_expr
    corr = (
        raw
        .filter(pl.col("feature").is_in(manifest_set))
        .with_columns(score_expr.alias("score_value"), side_signed_expr.alias("side_signed_value"))
        .filter(pl.col("score_value").is_not_null() & pl.col("score_value").is_finite())
    )
    return (
        corr.with_columns(
            pl.when(pl.col("target").is_in(DIRECTION_TARGETS)).then(pl.col("score_value")).otherwise(0.0).alias(
                "direction_candidate"
            ),
            pl.when(pl.col("target").is_in(DIRECTION_TARGETS))
            .then(pl.max_horizontal(pl.col("side_signed_value"), pl.lit(0.0)))
            .otherwise(0.0)
            .alias("direction_side_candidate"),
            pl.when(pl.col("target").is_in(WIDTH_TARGETS)).then(pl.col("score_value")).otherwise(0.0).alias(
                "width_candidate"
            ),
        )
        .group_by("feature")
        .agg(
            pl.max("direction_candidate").alias("direction_abs_spearman"),
            pl.max("direction_side_candidate").alias("direction_side_spearman"),
            pl.max("width_candidate").alias("width_abs_spearman"),
        )
    )


def load_bin_spread_evidence(diagnostics_root: Path, manifest_set: set[str], *, side: str) -> pl.DataFrame:
    inventory = diagnostics_root / "rpf_feature_diagnostic_inventory" / "manifest_feature_bin_spread_best.parquet"
    frames: list[pl.DataFrame] = []
    if inventory.exists():
        frames.append(pl.read_parquet(inventory))
    else:
        for path in diagnostics_root.glob("**/feature_bin_spreads.parquet"):
            try:
                frame = pl.read_parquet(path)
            except Exception:
                continue
            if {"feature", "target", "high_minus_low"}.issubset(frame.columns):
                frames.append(frame.with_columns(pl.col("high_minus_low").abs().alias("max_abs_bin_spread")))
    if not frames:
        return pl.DataFrame({"feature": [], "direction_abs_bin_spread": [], "direction_side_bin_spread": [], "width_abs_bin_spread": []})
    raw = pl.concat(frames, how="vertical_relaxed")
    if "median_bin_spread" in raw.columns:
        signed_expr = pl.col("median_bin_spread")
    elif "high_minus_low" in raw.columns:
        signed_expr = pl.col("high_minus_low")
    else:
        signed_expr = pl.lit(0.0)
    side_signed_expr = signed_expr if side == "up" else -signed_expr
    bins = (
        raw
        .filter(pl.col("feature").is_in(manifest_set))
        .with_columns(side_signed_expr.alias("side_signed_value"))
        .filter(pl.col("max_abs_bin_spread").is_not_null() & pl.col("max_abs_bin_spread").is_finite())
    )
    return (
        bins.with_columns(
            pl.when(pl.col("target").is_in(DIRECTION_TARGETS))
            .then(pl.col("max_abs_bin_spread"))
            .otherwise(0.0)
            .alias("direction_candidate"),
            pl.when(pl.col("target").is_in(DIRECTION_TARGETS))
            .then(pl.max_horizontal(pl.col("side_signed_value"), pl.lit(0.0)))
            .otherwise(0.0)
            .alias("direction_side_candidate"),
            pl.when(pl.col("target").is_in(WIDTH_TARGETS))
            .then(pl.col("max_abs_bin_spread"))
            .otherwise(0.0)
            .alias("width_candidate"),
        )
        .group_by("feature")
        .agg(
            pl.max("direction_candidate").alias("direction_abs_bin_spread"),
            pl.max("direction_side_candidate").alias("direction_side_bin_spread"),
            pl.max("width_candidate").alias("width_abs_bin_spread"),
        )
    )


def load_binary_selected_evidence(selected_feature_root: Path, manifest_set: set[str], target_col: str) -> pl.DataFrame:
    side = side_from_target(target_col)
    side_token = "up_ge_2x_down" if side == "up" else "down_ge_2x_up"
    frames: list[pl.DataFrame] = []
    for path in selected_feature_root.glob("rpf_clean_classification*/**/selected_features.parquet"):
        try:
            frame = pl.read_parquet(path)
        except Exception:
            continue
        if not {"target_col", "feature"}.issubset(frame.columns):
            continue
        columns = ["target_col", "feature"]
        if "pred_batch_id" in frame.columns:
            columns.append("pred_batch_id")
        frames.append(frame.select(columns).with_columns(pl.lit(str(path.parent)).alias("run_path")))
    if not frames:
        return empty_binary_selected_evidence()
    selected = (
        pl.concat(frames, how="vertical_relaxed")
        .filter(pl.col("feature").is_in(manifest_set))
        .filter(pl.col("target_col").str.contains(side_token))
    )
    if selected.is_empty():
        return empty_binary_selected_evidence()
    aggs = [pl.len().alias("binary_selected_count"), pl.n_unique("run_path").alias("binary_selected_runs")]
    if "pred_batch_id" not in selected.columns:
        selected = selected.with_columns(pl.lit(None).alias("pred_batch_id"))
    aggs.append(pl.col("pred_batch_id").drop_nulls().n_unique().alias("binary_selected_batches"))
    return selected.group_by("feature").agg(aggs)


def empty_binary_selected_evidence() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "feature": pl.String,
            "binary_selected_count": pl.UInt32,
            "binary_selected_runs": pl.UInt32,
            "binary_selected_batches": pl.UInt32,
        }
    )


def select_panel(
    evidence: pl.DataFrame,
    *,
    panel_kind: str,
    selected_count: int,
    per_family_limit: int,
    min_score: float,
) -> pl.DataFrame:
    score_col = {
        PANEL_DIRECTION_CORE: "direction_core_score",
        PANEL_BINARY_SELECTED: "binary_selected_score_total",
        PANEL_HYBRID_DIRECTION_BINARY: "hybrid_direction_binary_score",
        PANEL_WIDTH_CONTEXT: "width_context_score",
    }[panel_kind]
    allowed = KIND_ALLOWED_FAMILIES[panel_kind]
    scored = (
        evidence.filter(pl.col("family").is_in(allowed))
        .with_columns(pl.col(score_col).alias("panel_score"))
        .filter(pl.col("panel_score") >= float(min_score))
        .sort("panel_score", descending=True)
    )
    rows: list[dict[str, Any]] = []
    for _, group in scored.group_by("family", maintain_order=True):
        rows.extend(group.sort("panel_score", descending=True).head(per_family_limit).to_dicts())
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows, infer_schema_length=None).sort("panel_score", descending=True).head(selected_count)


def normalized_score_expr(column: str) -> pl.Expr:
    max_value = pl.max(column)
    return pl.when(max_value > 0).then(pl.col(column) / max_value).otherwise(0.0)


def side_token_expr(side: str) -> pl.Expr:
    pattern = side_token_pattern(side)
    return pl.col("feature").str.contains(pattern).cast(pl.Float64)


def opposite_side_token_expr(side: str) -> pl.Expr:
    return side_token_expr("down" if side == "up" else "up")


def side_token_pattern(side: str) -> str:
    if side == "up":
        return r"(^|_)up(_|$)|above|bull"
    if side == "down":
        return r"(^|_)down(_|$)|below|bear"
    raise ValueError(f"Unsupported side for evidence panel: {side}")


def feature_family(feature: str) -> str:
    for family, prefixes in FAMILY_PREFIXES.items():
        if feature.startswith(prefixes):
            return family
    return "unknown"


def panel_markdown(payload: dict[str, Any], panel: pl.DataFrame) -> str:
    lines = [
        "# RPF Evidence Feature Panel",
        "",
        f"- asset: `{payload['asset']}`",
        f"- root: `{payload['root']}`",
        f"- target: `{payload['target_col']}`",
        f"- panel kind: `{payload['panel_kind']}`",
        f"- selected features: `{payload['selected_feature_count']}`",
        f"- algorithm: `{payload['selection_algorithm']}`",
        "",
        "## Family Counts",
        "",
    ]
    family_counts = panel.group_by("family").len().sort("len", descending=True).to_dicts()
    lines.extend(f"- `{row['family']}`: `{row['len']}`" for row in family_counts)
    lines.extend(["", "## Selected Features", ""])
    for row in panel.select(
        [
            "feature",
            "family",
            "panel_score",
            "direction_abs_spearman",
            "direction_side_spearman",
            "direction_abs_bin_spread",
            "direction_side_bin_spread",
            "binary_selected_count",
            "width_abs_spearman",
            "side_token_score",
            "opposite_side_token_score",
        ]
    ).to_dicts():
        lines.append(
            "- "
            f"`{row['feature']}` "
            f"family=`{row['family']}` score=`{row['panel_score']:.6g}` "
            f"dir_spear=`{row['direction_abs_spearman']:.6g}` "
            f"side_spear=`{row['direction_side_spearman']:.6g}` "
            f"dir_spread=`{row['direction_abs_bin_spread']:.6g}` "
            f"side_spread=`{row['direction_side_bin_spread']:.6g}` "
            f"binary_count=`{row['binary_selected_count']}` "
            f"width_spear=`{row['width_abs_spearman']:.6g}` "
            f"side_token=`{row['side_token_score']}` "
            f"opposite_token=`{row['opposite_side_token_score']}`"
        )
    return "\n".join(lines) + "\n"


def run_root_for_args(args: argparse.Namespace, target_col: str) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_slug = target_col.replace("target_", "").replace("classification_", "")[:44]
    return Path(args.output_dir) / f"{now}_evidence_panel_{args.panel_kind}_{target_slug}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build RPF feature panels from saved diagnostics.")
    parser.add_argument("--asset", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--target-col", required=True)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--feature-ablation", default="all")
    parser.add_argument("--panel-kind", choices=PANEL_KINDS, default=PANEL_HYBRID_DIRECTION_BINARY)
    parser.add_argument("--selected-count", type=int, default=160)
    parser.add_argument("--per-family-limit", type=int, default=45)
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--diagnostics-root", type=Path, default=PROJECT_ROOT / "test_output")
    parser.add_argument("--selected-feature-root", type=Path, default=PROJECT_ROOT / "test_output")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
