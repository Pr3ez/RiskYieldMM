#!/usr/bin/env python3
"""Merge split HTF walk-forward diagnostics runs into one consolidated root."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analysis.htf_walkforward_diagnostics import (  # noqa: E402
    ROOTS,
    TARGET_COL,
    TF,
    _build_recommendations,
    _merge_feature_quality_frames,
    _root_slug,
)


ARTIFACT_KEYS = [
    "feature_importance_stability",
    "feature_noise_summary",
    "baseline_vs_filtered_root",
    "top_features_by_combo",
    "action_key_ranking",
]

TOP_LEVEL_AUDIT_FILES = [
    "workflow_manifest.json",
    "root_profiles.csv",
    "root_profiles.json",
    "root_profiles.parquet",
    "cross_root_summary.csv",
    "cross_root_summary.parquet",
    "causal_method_refresh.csv",
    "causal_method_refresh.parquet",
    "base_model_diagnostics.csv",
    "base_model_diagnostics.parquet",
]

OPTIONAL_AUDIT_FILES = [
    "research_sources.json",
    "implementation_note.txt",
]


@dataclass(frozen=True)
class BlockCandidate:
    source_root: Path
    source_dir: Path
    selection_scope: str
    feature_importance_type: str
    root_slug: str
    mtime: float


def _timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _parse_csv_tokens(raw: str) -> list[str]:
    return [token.strip() for token in str(raw).split(",") if token.strip()]


def _copy_file_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _discover_audit_root(base_dir: Path) -> Path:
    candidates: list[tuple[str, Path]] = []
    for root in sorted([p for p in base_dir.iterdir() if p.is_dir() and p.name.startswith("20")]):
        run_summary = root / "run_summary.json"
        if not run_summary.exists():
            continue
        try:
            payload = json.loads(run_summary.read_text(encoding="utf-8"))
        except Exception:
            continue
        phases = payload.get("phases")
        if phases == ["audit"]:
            candidates.append((root.name, root))
    if not candidates:
        raise FileNotFoundError("No audit-only diagnostics root found")
    return candidates[-1][1]


def _inventory_blocks(source_roots: list[Path]) -> dict[tuple[str, str, str], BlockCandidate]:
    selected: dict[tuple[str, str, str], BlockCandidate] = {}
    for source_root in source_roots:
        for summary_path in source_root.glob("step2/*/*/*/step2_summary.json"):
            source_dir = summary_path.parent
            rel = source_dir.relative_to(source_root / "step2")
            selection_scope, feature_importance_type, root_slug = rel.parts
            key = (selection_scope, feature_importance_type, root_slug)
            mtime = max((p.stat().st_mtime for p in source_dir.iterdir() if p.is_file()), default=0.0)
            candidate = BlockCandidate(
                source_root=source_root,
                source_dir=source_dir,
                selection_scope=selection_scope,
                feature_importance_type=feature_importance_type,
                root_slug=root_slug,
                mtime=mtime,
            )
            existing = selected.get(key)
            if existing is None or candidate.mtime > existing.mtime:
                selected[key] = candidate
    return selected


def _artifact_dest_paths(dest_dir: Path) -> dict[str, Path]:
    return {
        "feature_importance_stability": dest_dir / "feature_importance_stability.parquet",
        "feature_noise_summary": dest_dir / "feature_noise_summary.parquet",
        "baseline_vs_filtered_root": dest_dir / "baseline_vs_filtered_root.parquet",
        "top_features_by_combo": dest_dir / "top_features_by_combo.parquet",
        "action_key_ranking": dest_dir / "action_key_ranking.parquet",
    }


def _read_df(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge split HTF walk-forward diagnostics runs into one output root."
    )
    parser.add_argument("--project-root", type=str, default=str(PROJECT_ROOT))
    parser.add_argument(
        "--diagnostics-dir",
        type=str,
        default="test_output/htf_walkforward_diagnostics",
    )
    parser.add_argument(
        "--base-audit-root",
        type=str,
        default="",
        help="Optional path to the audit-only diagnostics root. Defaults to latest audit root.",
    )
    parser.add_argument(
        "--source-roots",
        type=str,
        default="",
        help="Optional comma-separated diagnostics roots to merge. Defaults to all other roots.",
    )
    parser.add_argument(
        "--output-root-name",
        type=str,
        default="",
        help="Optional explicit merged output root name under diagnostics-dir.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    diagnostics_dir = (project_root / args.diagnostics_dir).resolve()

    base_audit_root = (
        Path(args.base_audit_root).expanduser().resolve()
        if str(args.base_audit_root).strip()
        else _discover_audit_root(diagnostics_dir)
    )

    all_roots = sorted([p.resolve() for p in diagnostics_dir.iterdir() if p.is_dir() and p.name.startswith("20")])
    source_roots = (
        [Path(token).expanduser().resolve() for token in _parse_csv_tokens(args.source_roots)]
        if str(args.source_roots).strip()
        else [p for p in all_roots if p != base_audit_root]
    )

    output_root = (
        diagnostics_dir / args.output_root_name
        if str(args.output_root_name).strip()
        else diagnostics_dir / f"{_timestamp_tag()}_merged"
    )
    output_root.mkdir(parents=True, exist_ok=True)

    for name in TOP_LEVEL_AUDIT_FILES + OPTIONAL_AUDIT_FILES:
        _copy_file_if_exists(base_audit_root / name, output_root / name)

    workflow_manifest_path = output_root / "workflow_manifest.json"
    root_profiles_path = output_root / "root_profiles.parquet"
    cross_root_summary_path = output_root / "cross_root_summary.parquet"
    causal_method_refresh_path = output_root / "causal_method_refresh.parquet"

    workflow_manifest = json.loads(workflow_manifest_path.read_text(encoding="utf-8"))
    root_profiles = pl.read_parquet(root_profiles_path)

    root_by_slug = {_root_slug(root): root for root in ROOTS}
    selected_blocks = _inventory_blocks(source_roots)

    missing_blocks: list[dict[str, str]] = []
    step2_manifests: dict[str, dict[str, dict[str, Any]]] = {}
    feature_quality_by_root: dict[str, pl.DataFrame] = {}
    top_features_by_root: dict[str, list[str]] = {}
    phase_rows_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    step2_aggregate_rows: list[dict[str, Any]] = []
    winner_vs_near_overlap_rows: list[pl.DataFrame] = []

    expected_scopes = ["winner_only", "root_topk"]
    expected_types = ["PredictionValuesChange", "LossFunctionChange"]

    for scope in expected_scopes:
        for imp_type in expected_types:
            for root_slug, root in root_by_slug.items():
                block = selected_blocks.get((scope, imp_type, root_slug))
                if block is None:
                    missing_blocks.append(
                        {
                            "selection_scope": scope,
                            "feature_importance_type": imp_type,
                            "root": root,
                        }
                    )
                    continue

                dest_dir = output_root / "step2" / scope / imp_type / root_slug
                shutil.copytree(block.source_dir, dest_dir, dirs_exist_ok=True)

                fq_name_csv = f"{scope}_{imp_type}_feature_quality.csv"
                fq_name_parquet = f"{scope}_{imp_type}_feature_quality.parquet"
                fq_src_csv = block.source_root / "feature_quality" / root_slug / fq_name_csv
                fq_src_parquet = block.source_root / "feature_quality" / root_slug / fq_name_parquet
                _copy_file_if_exists(
                    fq_src_csv,
                    output_root / "feature_quality" / root_slug / fq_name_csv,
                )
                _copy_file_if_exists(
                    fq_src_parquet,
                    output_root / "feature_quality" / root_slug / fq_name_parquet,
                )

                summary_path = dest_dir / "step2_summary.json"
                unit_summary = json.loads(summary_path.read_text(encoding="utf-8"))
                step2_manifests.setdefault(scope, {}).setdefault(imp_type, {})[root] = {
                    "source_run_root": str(block.source_root),
                    "units": {f"{TF}/{TARGET_COL}": unit_summary},
                }

                artifact_paths = _artifact_dest_paths(dest_dir)
                artifact_frames: dict[str, pl.DataFrame] = {}
                for artifact_key, artifact_path in artifact_paths.items():
                    if artifact_path.exists():
                        phase_rows_by_key[(scope, imp_type)].append(
                            {
                                "root": root,
                                "selection_scope": scope,
                                "feature_importance_type": imp_type,
                                "artifact_type": artifact_key,
                                "path": str(artifact_path),
                            }
                        )
                    art_df = _read_df(artifact_path)
                    if art_df.is_empty():
                        continue
                    enriched = art_df.with_columns(
                        [
                            pl.lit(root).alias("root"),
                            pl.lit(scope).alias("selection_scope"),
                            pl.lit(imp_type).alias("feature_importance_type"),
                        ]
                    )
                    artifact_frames[artifact_key] = enriched
                    step2_aggregate_rows.append(
                        {
                            "root": root,
                            "selection_scope": scope,
                            "feature_importance_type": imp_type,
                            "artifact_type": artifact_key,
                            "path": str(artifact_path),
                            "rows": int(enriched.height),
                        }
                    )

                top_df = artifact_frames.get("top_features_by_combo", pl.DataFrame())
                if not top_df.is_empty() and "feature" in top_df.columns:
                    top_features = sorted(set(top_df["feature"].unique().to_list()))
                    top_features_by_root[root] = sorted(
                        set(top_features_by_root.get(root, [])) | set(top_features)
                    )

                fq_dest = output_root / "feature_quality" / root_slug / fq_name_parquet
                fq_df = _read_df(fq_dest)
                if not fq_df.is_empty():
                    feature_quality_by_root[root] = _merge_feature_quality_frames(
                        feature_quality_by_root.get(root),
                        fq_df,
                    )

                if scope == "root_topk":
                    overlap_path = dest_dir / "winner_vs_near_winner_overlap.parquet"
                    overlap_df = _read_df(overlap_path)
                    if not overlap_df.is_empty():
                        winner_vs_near_overlap_rows.append(overlap_df)

    for (scope, imp_type), rows in phase_rows_by_key.items():
        if not rows:
            continue
        phase_df = pl.DataFrame(rows).sort(["feature_importance_type", "root", "artifact_type"])
        phase_df.write_csv(output_root / f"step2_{scope}_{imp_type}_artifacts.csv")

    if step2_aggregate_rows:
        step2_aggregate_df = pl.DataFrame(step2_aggregate_rows).sort(
            ["selection_scope", "feature_importance_type", "root", "artifact_type"]
        )
        step2_aggregate_df.write_csv(output_root / "step2_aggregate_artifacts.csv")
        step2_aggregate_df.write_parquet(output_root / "step2_aggregate_artifacts.parquet")

    if winner_vs_near_overlap_rows:
        overlap_df = pl.concat(winner_vs_near_overlap_rows, how="diagonal_relaxed").sort(
            ["feature_importance_type", "root", "compare_action_key"]
        )
        overlap_df.write_csv(output_root / "winner_vs_near_winner_overlap.csv")
        overlap_df.write_parquet(output_root / "winner_vs_near_winner_overlap.parquet")

    recommendations = _build_recommendations(
        root_profiles=root_profiles,
        feature_quality_by_root=feature_quality_by_root,
        top_features_by_root=top_features_by_root,
    )
    if not recommendations.is_empty():
        recommendations.write_csv(output_root / "recommendations.csv")
        recommendations.write_parquet(output_root / "recommendations.parquet")

    merge_manifest = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_audit_root": str(base_audit_root),
        "source_roots": [str(p) for p in source_roots],
        "selected_blocks": [
            {
                "selection_scope": scope,
                "feature_importance_type": imp_type,
                "root": root_by_slug[root_slug],
                "source_root": str(block.source_root),
                "source_dir": str(block.source_dir),
            }
            for (scope, imp_type, root_slug), block in sorted(selected_blocks.items())
            if root_slug in root_by_slug
        ],
        "missing_blocks": missing_blocks,
    }
    (output_root / "merge_manifest.json").write_text(
        json.dumps(merge_manifest, indent=2),
        encoding="utf-8",
    )

    run_summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "output_root": str(output_root),
        "workflow_manifest": str(workflow_manifest_path),
        "root_profiles": str(root_profiles_path),
        "cross_root_summary": str(output_root / "cross_root_summary.csv"),
        "causal_method_refresh": str(output_root / "causal_method_refresh.csv"),
        "step2_manifests": step2_manifests,
        "roots": sorted(ROOTS.keys()),
        "phases": expected_scopes,
        "feature_importance_types": expected_types,
        "merged_from": [str(base_audit_root)] + [str(p) for p in source_roots],
        "merge_manifest": str(output_root / "merge_manifest.json"),
        "missing_blocks": missing_blocks,
    }
    (output_root / "run_summary.json").write_text(
        json.dumps(run_summary, indent=2),
        encoding="utf-8",
    )

    print(f"Merged diagnostics root: {output_root}")
    print(f"Selected blocks: {len(selected_blocks)}")
    print(f"Missing blocks: {len(missing_blocks)}")
    for row in missing_blocks:
        print(
            "  MISSING "
            f"{row['selection_scope']} | {row['feature_importance_type']} | {row['root']}"
        )


if __name__ == "__main__":
    main()
