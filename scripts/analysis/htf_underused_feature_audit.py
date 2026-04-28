from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl


PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
DEFAULT_MERGED_ROOT = (
    PROJECT_ROOT
    / "test_output"
    / "htf_walkforward_diagnostics"
    / "20260411_153744_merged"
)
DEFAULT_OUTPUT_BASE = PROJECT_ROOT / "test_output" / "htf_underused_feature_audit"
ROOT_SLUGS = ("8h_b", "8h_c", "24h_b", "24h_c", "7d_b", "7d_c")
META_FEATURES_TO_IGNORE = {
    "family_batch_id",
    "family_bar_pos",
    "source_base_batch_id",
    "entry_window_hours",
    "family_shift_hours",
    "batch_duration_hours",
    "is_label_half",
}


def _feature_family(feature: str) -> str:
    if feature in {"open", "high", "low", "close", "volume"}:
        return "ohlcv"
    if feature.startswith("H_"):
        return "helper"
    if feature.startswith("X_D_"):
        return "x_derivatives_pressure"
    if feature.startswith("D_"):
        return "distance"
    if feature.startswith("F_I_"):
        return "funding"
    if feature.startswith("D_F_"):
        return "premium"
    if feature.startswith("S_"):
        return "sentiment"
    if feature.startswith("L_"):
        return "volume_flow_oi"
    if feature.startswith("M_"):
        return "momentum_trend"
    if feature.startswith("N_"):
        return "normalized_position"
    if feature.startswith("V_"):
        return "volatility_risk_shape"
    if feature.startswith("C_") or feature.startswith("B_"):
        return "candlestick_direction"
    return "other"


def _load_root_frame(merged_root: Path, root_slug: str) -> pl.DataFrame:
    stability = pl.read_parquet(
        merged_root
        / "step2"
        / "root_topk"
        / "PredictionValuesChange"
        / root_slug
        / "feature_importance_stability.parquet"
    )
    quality = pl.read_parquet(
        merged_root
        / "feature_quality"
        / root_slug
        / "root_topk_PredictionValuesChange_feature_quality.parquet"
    )
    return (
        stability.join(
            quality.select(
                [
                    "feature",
                    "null_rate",
                    "drift_score",
                    "drift_level",
                    "policy_blocked",
                    "suspicious",
                    "suspicious_reason",
                ]
            ),
            on="feature",
            how="left",
        )
        .with_columns(
            [
                pl.lit(root_slug.replace("_", "/")).alias("root"),
                pl.col("feature").map_elements(
                    _feature_family,
                    return_dtype=pl.String,
                ).alias("feature_family"),
                pl.col("null_rate").fill_null(0.0),
                pl.col("policy_blocked").fill_null(False),
                pl.col("suspicious").fill_null(False),
            ]
        )
        .filter(~pl.col("feature").is_in(META_FEATURES_TO_IGNORE))
    )


def build_underused_audit(merged_root: Path) -> dict[str, pl.DataFrame]:
    all_df = pl.concat([_load_root_frame(merged_root, slug) for slug in ROOT_SLUGS])

    suspiciously_underused_clean = (
        all_df.filter(pl.col("selected_step_freq") <= 0.15)
        .filter(pl.col("mean_importance") <= 0.25)
        .filter(pl.col("null_rate") <= 0.05)
        .filter(~pl.col("policy_blocked"))
        .filter(~pl.col("suspicious"))
        .filter((pl.col("drift_level").is_null()) | (pl.col("drift_level") != "high"))
        .sort(["root", "selected_step_freq", "mean_importance"])
    )

    expected_underused = (
        all_df.filter(pl.col("selected_step_freq") <= 0.15)
        .filter(
            (pl.col("null_rate") > 0.05)
            | pl.col("policy_blocked")
            | pl.col("suspicious")
            | (pl.col("drift_level") == "high")
        )
        .sort(["root", "selected_step_freq", "null_rate"], descending=[False, False, True])
    )

    family_summary = (
        all_df.group_by(["root", "feature_family"])
        .agg(
            [
                pl.len().alias("n_features"),
                pl.col("selected_step_freq").mean().alias("mean_selected_step_freq"),
                pl.col("mean_importance").mean().alias("mean_importance"),
                pl.col("null_rate").mean().alias("mean_null_rate"),
                (pl.col("selected_step_freq") <= 0.15).sum().alias("n_low_usage"),
                (
                    (pl.col("selected_step_freq") <= 0.15)
                    & (pl.col("null_rate") <= 0.05)
                    & (~pl.col("policy_blocked"))
                    & (~pl.col("suspicious"))
                    & ((pl.col("drift_level").is_null()) | (pl.col("drift_level") != "high"))
                ).sum().alias("n_clean_low_usage"),
            ]
        )
        .sort(["root", "mean_selected_step_freq"])
    )

    consistently_underused_clean = (
        all_df.group_by("feature")
        .agg(
            [
                pl.len().alias("root_count"),
                pl.col("selected_step_freq").mean().alias("mean_selected_step_freq"),
                pl.col("mean_importance").mean().alias("mean_importance"),
                pl.col("null_rate").mean().alias("mean_null_rate"),
                (pl.col("selected_step_freq") <= 0.15).sum().alias("roots_low_usage"),
                (
                    (pl.col("null_rate") <= 0.05)
                    & (~pl.col("policy_blocked"))
                    & (~pl.col("suspicious"))
                    & ((pl.col("drift_level").is_null()) | (pl.col("drift_level") != "high"))
                ).sum().alias("roots_clean_ok"),
                pl.first("feature_family").alias("feature_family"),
            ]
        )
        .filter(pl.col("roots_low_usage") >= 4)
        .filter(pl.col("roots_clean_ok") >= 4)
        .sort(["roots_low_usage", "mean_selected_step_freq", "mean_importance"], descending=[True, False, False])
    )

    key_expected_features = [
        "volume",
        "C_N_bodySize_bnd",
        "C_N_upperShadow_bnd",
        "C_N_lowerShadow_bnd",
        "B_C_candleDirection_bin",
        "B_consecutiveUp_bnd",
        "B_consecutiveDown_bnd",
        "M_N_rsi_short_bnd",
        "M_N_rsi_med_bnd",
        "M_N_rsi_long_bnd",
        "N_M_cci_short_zsc",
        "N_M_cci_med_zsc",
        "M_V_sharpe_long_rat",
        "M_V_sharpe_xlong_rat",
        "M_V_sortino_long_rat",
        "M_V_sortino_xlong_rat",
        "L_N_volumeRatio_short_rat",
        "L_N_volumeRatio_med_rat",
        "L_N_volumeRatio_long_rat",
        "L_M_N_volumeRoc_short_pct",
        "L_M_N_volumeRoc_med_pct",
        "L_M_N_volumeRoc_long_pct",
    ]
    expected_feature_panel = (
        all_df.filter(pl.col("feature").is_in(key_expected_features))
        .select(
            [
                "root",
                "feature",
                "feature_family",
                "selected_step_freq",
                "mean_importance",
                "null_rate",
                "drift_level",
            ]
        )
        .sort(["feature", "root"])
    )

    return {
        "all_features": all_df,
        "suspiciously_underused_clean": suspiciously_underused_clean,
        "expected_underused": expected_underused,
        "family_summary": family_summary,
        "consistently_underused_clean": consistently_underused_clean,
        "expected_feature_panel": expected_feature_panel,
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
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-root", type=Path, default=DEFAULT_MERGED_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_BASE)
    args = parser.parse_args()

    frames = build_underused_audit(args.merged_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = args.output_dir / timestamp
    write_outputs(output_root, frames, args.merged_root)
    print(output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
