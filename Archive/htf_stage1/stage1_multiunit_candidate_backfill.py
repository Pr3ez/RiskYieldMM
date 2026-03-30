#!/usr/bin/env python3
"""Backfill Stage-1 candidate coverage for remaining units (append-only).

Goal:
- Ensure selected candidate combos have per-step pred payload coverage.
- Use exact Stage-1 Step-1 evaluation path (`evaluate_stage1_grid`, append_mode=True).
- Preserve existing artifacts (append only), then report coverage before/after.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

# Ensure project root is importable when running script from subdirectory path.
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT_IMPORT = _THIS_FILE.parents[1]
if str(_PROJECT_ROOT_IMPORT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_IMPORT))

from scripts.htf_backtest.catboost.stage1_optimizer import evaluate_stage1_grid
from scripts.htf_backtest.catboost.stage1_runner import (
    _stage1_get_step_winner_metrics,
    _stage1_step_artifact_status,
    _stage1_update_step_summary_quality,
    run_walk_forward_stage1_grid,
)
from scripts.htf_backtest.catboost.tf_15m import (
    Config15m,
    FeatureSpace15m,
    ModelSpace15m,
    Optimizer15m,
    WindowSpace15m,
)
from scripts.htf_backtest.catboost.tf_1m import (
    Config1m,
    FeatureSpace1m,
    ModelSpace1m,
    Optimizer1m,
    WindowSpace1m,
)
from scripts.htf_backtest.catboost.tf_5m import (
    Config5m,
    FeatureSpace5m,
    ModelSpace5m,
    Optimizer5m,
    WindowSpace5m,
)
from scripts.htf_backtest.configuration import build_backtest_maps


DEFAULT_PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
DEFAULT_RUN_ID = "stage1_catboost_live"
DEFAULT_MODEL_NAME = "catboost"
DEFAULT_UNITS = [
    "1m/target_breakfree",
    "5m/target_4class",
    "5m/target_breakfree",
    "15m/target_4class",
    "15m/target_breakfree",
]
DEFAULT_SOURCE_SCOPE = "current+archive"
CLASS_NAMES_4 = [
    "DOWN_BALANCED",
    "DOWN_EXPANSION",
    "UP_BALANCED",
    "UP_EXPANSION",
]
CLASS_NAMES_BREAKFREE = [
    "UP_ABOVE_BREAKFREE",
    "DOWN_ABOVE_BREAKFREE",
    "IN_BETWEEN_BELOW_BREAKFREE",
]
STAGE1_CB_BASE_PARAMS = {
    "loss_function": "MultiClass",
    "eval_metric": "MultiClass",
    "task_type": "GPU",
    "devices": "0",
    "random_seed": 42,
    "allow_writing_files": False,
    "verbose": False,
    "thread_count": -1,
    "bootstrap_type": "Bernoulli",
}
STAGE1_LOOKBACK_MAX_BY_TF = {"1m": 450, "5m": 450, "15m": 450}
STAGE1_MIN_SAMPLES_BY_TF = {"1m": 150, "5m": 100, "15m": 50}
ACTION_KEY_PATTERN = re.compile(r"^f(?P<f>\d+)_v(?P<v>\d+)_t(?P<t>\d+)$")


TF_CLASS_MAP = {
    "1m": {
        "config_cls": Config1m,
        "window_cls": WindowSpace1m,
        "feature_cls": FeatureSpace1m,
        "model_cls": ModelSpace1m,
        "optimizer_cls": Optimizer1m,
    },
    "5m": {
        "config_cls": Config5m,
        "window_cls": WindowSpace5m,
        "feature_cls": FeatureSpace5m,
        "model_cls": ModelSpace5m,
        "optimizer_cls": Optimizer5m,
    },
    "15m": {
        "config_cls": Config15m,
        "window_cls": WindowSpace15m,
        "feature_cls": FeatureSpace15m,
        "model_cls": ModelSpace15m,
        "optimizer_cls": Optimizer15m,
    },
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill missing step/candidate pairs for Stage-1 selected candidates "
            "using append-only evaluate_stage1_grid."
        )
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=str(DEFAULT_PROJECT_ROOT),
        help=f"Project root (default: {DEFAULT_PROJECT_ROOT})",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=DEFAULT_RUN_ID,
        help=f"Stage-1 run id (default: {DEFAULT_RUN_ID})",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help=f"Model folder (default: {DEFAULT_MODEL_NAME})",
    )
    parser.add_argument(
        "--units",
        nargs="*",
        default=DEFAULT_UNITS,
        help="Units (<tf>/<target>) space/comma separated.",
    )
    parser.add_argument(
        "--candidate-run-dir",
        type=str,
        default="",
        help=(
            "Candidate-search run directory path or folder name under "
            "catboost/candidate_search_v2. Defaults to latest run."
        ),
    )
    parser.add_argument(
        "--candidate-fallback-from-winners",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "If a unit is missing candidate12 files in candidate-run-dir, allow strict fallback "
            "from unit winner artifacts (expects exactly 12 action keys). "
            "Use --no-candidate-fallback-from-winners to disable."
        ),
    )
    parser.add_argument(
        "--source-scope",
        type=str,
        default=DEFAULT_SOURCE_SCOPE,
        choices=["current", "archive", "current+archive"],
        help=f"Coverage scope (default: {DEFAULT_SOURCE_SCOPE})",
    )
    parser.add_argument(
        "--preflight-diagnostic",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Run fast stage integrity diagnostic on existing step folders before "
            "ensure/backfill (default: True). Use --no-preflight-diagnostic to disable."
        ),
    )
    parser.add_argument(
        "--preflight-fail-on-broken",
        action="store_true",
        help=(
            "Fail run after preflight if broken steps are found "
            "(missing artifacts, unreadable summary, missing expected combos)."
        ),
    )
    parser.add_argument(
        "--preflight-auto-fix-broken",
        action="store_true",
        help=(
            "If preflight finds broken steps, auto-continue into Stage-1 ensure/rebuild "
            "flow instead of exiting. When ensure n_steps is 0, script auto-sets "
            "ensure steps from discovered coverage."
        ),
    )
    parser.add_argument(
        "--ensure-stage1-steps",
        type=int,
        default=0,
        help=(
            "If >0, run Stage-1 walk-forward generation first (resume mode) "
            "to ensure selected units have step folders up to this n_steps window."
        ),
    )
    parser.add_argument(
        "--ensure-stage1-resume-mode",
        type=str,
        default="skip_completed",
        choices=["continue", "skip_completed"],
        help="Resume mode for pre-backfill Stage-1 generation (default: skip_completed).",
    )
    parser.add_argument(
        "--ensure-stage1-debug-batches",
        action="store_true",
        help="Enable debug batch prints during pre-backfill Stage-1 generation.",
    )
    parser.add_argument(
        "--ensure-stage1-serial-units",
        action="store_true",
        help=(
            "Run ensure-stage1 one unit at a time (all steps for each unit sequentially), "
            "instead of grouped multi-unit walk-forward."
        ),
    )
    parser.add_argument(
        "--ensure-stage1-probe-enabled",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Enable Stage-1 probe tiers during ensure generation (default: True). "
            "Use --no-ensure-stage1-probe-enabled to disable probe enrichment."
        ),
    )
    parser.add_argument(
        "--ensure-stage1-backfill-low-quality-completed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "When probe is enabled, allow probe enrichment on completed low-quality steps "
            "(default: True). Use --no-ensure-stage1-backfill-low-quality-completed to skip."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute backfill. Without this flag, only coverage audit is produced.",
    )
    parser.add_argument(
        "--candidate-source",
        type=str,
        default="candidate12_backfill",
        help="Metadata candidate_source passed to evaluate_stage1_grid.",
    )
    parser.add_argument(
        "--discovered-from",
        type=str,
        default="stage1_multiunit_candidate_backfill",
        help="Metadata discovered_from passed to evaluate_stage1_grid.",
    )
    parser.add_argument(
        "--max-steps-per-unit",
        type=int,
        default=0,
        help="Optional limit of missing pred_batches to process per unit (0 = all).",
    )
    parser.add_argument(
        "--output-tag",
        type=str,
        default="",
        help="Optional suffix for output run directory.",
    )
    parser.add_argument(
        "--rerun-candidate-search",
        action="store_true",
        help="After backfill, re-run stage1_multiunit_candidate_search.py for the same units.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-step progress.",
    )
    parser.add_argument(
        "--progress-every-steps",
        type=int,
        default=10,
        help="Progress heartbeat cadence during apply mode (default: 10).",
    )
    parser.add_argument(
        "--augment-proportional-f1",
        action="store_true",
        help=(
            "Add derived non-fold candidates f1_v{val}_t{train} per unit, "
            "based on existing candidate12 val/train proportions."
        ),
    )
    parser.add_argument(
        "--f1-max-extra-per-unit",
        type=int,
        default=12,
        help="Maximum number of derived proportional f1 candidates to add per unit (default: 12).",
    )
    parser.add_argument(
        "--f1-augment-include-fold-scaled",
        action="store_true",
        help=(
            "When deriving proportional f1 candidates, also include fold-scaled variants "
            "f1_v{fold*val}_t{fold*train} to increase unique f1 coverage."
        ),
    )
    return parser.parse_args()


def _normalize_units(raw_units: list[str]) -> list[str]:
    units: list[str] = []
    for raw in raw_units:
        for part in str(raw).split(","):
            unit = part.strip()
            if not unit:
                continue
            if "/" not in unit:
                raise ValueError(f"Invalid unit format: {unit!r}")
            units.append(unit)
    out: list[str] = []
    seen: set[str] = set()
    for unit in units:
        if unit not in seen:
            seen.add(unit)
            out.append(unit)
    return out


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_json(v) for v in value]
    if isinstance(value, tuple):
        return [_safe_json(v) for v in value]
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_safe_json(payload), f, indent=2, ensure_ascii=False)


def _resolve_candidate_run_dir(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    candidate_run_dir_arg: str,
) -> Path:
    search_root = (
        project_root
        / "data"
        / "htf_backtest_results"
        / run_id
        / model_name
        / "candidate_search_v2"
    )
    if not search_root.exists():
        raise FileNotFoundError(f"candidate_search_v2 root not found: {search_root}")

    if candidate_run_dir_arg:
        direct = Path(candidate_run_dir_arg).expanduser()
        if direct.exists():
            return direct.resolve()
        child = search_root / candidate_run_dir_arg
        if child.exists():
            return child.resolve()
        raise FileNotFoundError(
            f"candidate run dir not found: {candidate_run_dir_arg!r} "
            f"(checked {direct} and {child})"
        )

    runs = sorted([p for p in search_root.glob("run_*") if p.is_dir()])
    if not runs:
        raise FileNotFoundError(f"No candidate_search_v2 runs found in {search_root}")
    return runs[-1].resolve()


def _iter_snapshot_paths(step_stage1_dir: Path, scope: str):
    include_current = scope in {"current", "current+archive"}
    include_archive = scope in {"archive", "current+archive"}

    if include_current:
        combo_path = step_stage1_dir / "stage1_combo_index.parquet"
        pred_path = step_stage1_dir / "stage1_pred_batch_predictions.parquet"
        if combo_path.exists() and pred_path.exists():
            yield "current", combo_path, pred_path

    if include_archive:
        archive_root = step_stage1_dir / "archive_legacy"
        if archive_root.exists():
            for snap_dir in sorted([p for p in archive_root.iterdir() if p.is_dir()]):
                combo_path = snap_dir / "stage1_combo_index.parquet"
                pred_path = snap_dir / "stage1_pred_batch_predictions.parquet"
                if combo_path.exists() and pred_path.exists():
                    yield f"archive:{snap_dir.name}", combo_path, pred_path


def _present_actions_from_snapshot(combo_path: Path, pred_path: Path) -> set[str]:
    try:
        combo_df = pl.read_parquet(combo_path)
        pred_df = pl.read_parquet(pred_path)
    except Exception:
        return set()
    if combo_df.is_empty() or pred_df.is_empty():
        return set()
    if "scope" in pred_df.columns:
        pred_df = pred_df.filter(pl.col("scope") == "pred_batch")
    if pred_df.is_empty():
        return set()
    if not {"combo_id", "action_key"}.issubset(set(combo_df.columns)):
        return set()
    if "combo_id" not in pred_df.columns:
        return set()

    combo_map = (
        combo_df.select(["combo_id", "action_key"])
        .with_columns(
            [
                pl.col("combo_id").cast(pl.Int64, strict=False),
                pl.col("action_key").cast(pl.Utf8, strict=False),
            ]
        )
        .drop_nulls(["combo_id", "action_key"])
        .unique(subset=["combo_id"], keep="first")
    )
    pred_combo_ids = (
        pred_df.select("combo_id")
        .with_columns(pl.col("combo_id").cast(pl.Int64, strict=False))
        .drop_nulls(["combo_id"])
        .unique()
    )
    joined = pred_combo_ids.join(combo_map, on="combo_id", how="inner")
    return {
        str(v)
        for v in joined["action_key"].to_list()
        if v is not None and str(v).strip() != ""
    }


def _scan_candidate_coverage(
    *,
    unit_dir: Path,
    required_action_keys: list[str],
    scope: str,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    required_sorted = sorted({str(v) for v in required_action_keys if str(v).strip()})
    required_set = set(required_sorted)

    coverage_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []

    batch_dirs = sorted(
        [p for p in unit_dir.glob("batch_*") if p.is_dir()],
        key=lambda p: int(p.name.split("_")[1]),
    )
    for batch_dir in batch_dirs:
        pred_batch = int(batch_dir.name.split("_")[1])
        step_stage1_dir = batch_dir / "stage1"
        present = set()
        snapshots_seen = 0
        for _, combo_path, pred_path in _iter_snapshot_paths(step_stage1_dir, scope):
            snapshots_seen += 1
            present |= _present_actions_from_snapshot(combo_path, pred_path)
        present_required = sorted(required_set & present)
        missing = sorted(required_set - set(present_required))
        coverage_rows.append(
            {
                "pred_batch": pred_batch,
                "required_count": len(required_sorted),
                "present_count": len(present_required),
                "missing_count": len(missing),
                "missing_action_keys": json.dumps(missing),
                "snapshots_seen": snapshots_seen,
            }
        )
        for action_key in missing:
            missing_rows.append(
                {
                    "pred_batch": pred_batch,
                    "action_key": action_key,
                }
            )

    coverage_df = (
        pl.DataFrame(coverage_rows)
        if coverage_rows
        else pl.DataFrame(
            schema={
                "pred_batch": pl.Int64,
                "required_count": pl.Int64,
                "present_count": pl.Int64,
                "missing_count": pl.Int64,
                "missing_action_keys": pl.Utf8,
                "snapshots_seen": pl.Int64,
            }
        )
    )
    if not coverage_df.is_empty():
        coverage_df = (
            coverage_df.sort("pred_batch")
            .with_row_index(name="step_idx", offset=1)
            .select(
                [
                    "pred_batch",
                    "step_idx",
                    "required_count",
                    "present_count",
                    "missing_count",
                    "missing_action_keys",
                    "snapshots_seen",
                ]
            )
        )

    missing_df = (
        pl.DataFrame(missing_rows)
        if missing_rows
        else pl.DataFrame(schema={"pred_batch": pl.Int64, "action_key": pl.Utf8})
    )
    if not missing_df.is_empty():
        missing_df = missing_df.sort(["pred_batch", "action_key"])
    return coverage_df, missing_df


def _dataclass_from_snapshot(cls, raw: dict[str, Any]) -> Any:
    allowed = {f.name for f in fields(cls)}
    src = dict(raw or {})
    kwargs = {k: src[k] for k in src if k in allowed}
    if "project_root" in kwargs and kwargs["project_root"] is not None:
        kwargs["project_root"] = Path(str(kwargs["project_root"]))
    if "class_names" in kwargs and isinstance(kwargs["class_names"], list):
        kwargs["class_names"] = tuple(kwargs["class_names"])
    if "class_weight_choices" in kwargs and isinstance(kwargs["class_weight_choices"], list):
        kwargs["class_weight_choices"] = tuple(str(v) for v in kwargs["class_weight_choices"])
    if "cb_base_params" in kwargs and kwargs["cb_base_params"] is not None:
        kwargs["cb_base_params"] = dict(kwargs["cb_base_params"])
    return cls(**kwargs)


def _load_step_optimizer_from_snapshot(*, tf: str, snapshot_path: Path) -> tuple[Any, Any]:
    tf_map = TF_CLASS_MAP.get(tf)
    if tf_map is None:
        raise ValueError(f"Unsupported timeframe for backfill: {tf}")

    with open(snapshot_path, encoding="utf-8") as f:
        snapshot = json.load(f)

    cfg = _dataclass_from_snapshot(tf_map["config_cls"], snapshot.get("config", {}))
    win = _dataclass_from_snapshot(tf_map["window_cls"], snapshot.get("window_space", {}))
    feat = _dataclass_from_snapshot(tf_map["feature_cls"], snapshot.get("feature_space", {}))
    model = _dataclass_from_snapshot(tf_map["model_cls"], snapshot.get("model_space", {}))

    optimizer = tf_map["optimizer_cls"](
        config=cfg,
        window_space=win,
        feature_space=feat,
        model_space=model,
    )
    step_optimizer = optimizer.create_step_optimizer()
    return cfg, step_optimizer


def _parse_action_key_triplet(action_key: str) -> tuple[int, int, int] | None:
    m = ACTION_KEY_PATTERN.fullmatch(str(action_key).strip())
    if m is None:
        return None
    return (
        int(m.group("f")),
        int(m.group("v")),
        int(m.group("t")),
    )


def _mapping_from_action_keys(
    *,
    action_keys: list[str],
    unit: str,
    source_path: Path,
) -> dict[str, tuple[int, int, int]]:
    mapping: dict[str, tuple[int, int, int]] = {}
    bad_keys: list[str] = []
    for action_key in sorted({str(v) for v in action_keys if str(v).strip()}):
        tri = _parse_action_key_triplet(action_key)
        if tri is None:
            bad_keys.append(str(action_key))
            continue
        mapping[str(action_key)] = (int(tri[0]), int(tri[1]), int(tri[2]))

    if bad_keys:
        examples = bad_keys[:8]
        raise ValueError(
            f"{unit} has invalid action_key format in {source_path}: {examples}"
        )
    if len(mapping) != 12:
        raise ValueError(
            f"{unit} candidate set size must be 12, got {len(mapping)} ({source_path})"
        )
    return mapping


def _load_winner_fallback_candidate_map(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
) -> tuple[dict[str, tuple[int, int, int]], Path] | None:
    tf, target = unit.split("/", 1)
    unit_dir = project_root / "data" / "htf_backtest_results" / run_id / model_name / tf / target
    if not unit_dir.exists():
        return None

    # Preferred fallback: winners combo stats contain exactly the selected winner set.
    stats_path = unit_dir / "winners_combo_stats.parquet"
    if stats_path.exists():
        df = pl.read_parquet(stats_path)
        col = "winner_combo_key" if "winner_combo_key" in df.columns else (
            "action_key" if "action_key" in df.columns else None
        )
        if col is not None:
            keys = [str(v) for v in df[col].drop_nulls().to_list() if str(v).strip()]
            mapping = _mapping_from_action_keys(
                action_keys=keys,
                unit=unit,
                source_path=stats_path,
            )
            return mapping, stats_path

    # Secondary fallback: winners_all_steps can be collapsed to unique action keys.
    winners_path = unit_dir / "winners_all_steps.parquet"
    if winners_path.exists():
        df = pl.read_parquet(winners_path)
        col = "winner_combo_key" if "winner_combo_key" in df.columns else (
            "action_key" if "action_key" in df.columns else None
        )
        if col is not None:
            keys = [str(v) for v in df[col].drop_nulls().unique().to_list() if str(v).strip()]
            mapping = _mapping_from_action_keys(
                action_keys=keys,
                unit=unit,
                source_path=winners_path,
            )
            return mapping, winners_path

    return None


def _load_candidate_map(
    candidate_run_dir: Path,
    units: list[str],
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    allow_winner_fallback: bool,
) -> dict[str, dict[str, tuple[int, int, int]]]:
    out: dict[str, dict[str, tuple[int, int, int]]] = {}
    for unit in units:
        tf, target = unit.split("/", 1)
        candidate_path = candidate_run_dir / tf / target / "candidate12_v2.parquet"
        mapping: dict[str, tuple[int, int, int]] | None = None
        source_path: Path | None = None

        if candidate_path.exists():
            df = pl.read_parquet(candidate_path)
            required_cols = {
                "action_key",
                "fold_count",
                "val_batches_per_fold",
                "train_batches_per_fold",
            }
            missing_cols = sorted(required_cols - set(df.columns))
            if missing_cols:
                raise ValueError(f"{candidate_path} missing columns: {missing_cols}")
            mapping = {}
            for row in df.iter_rows(named=True):
                action_key = str(row["action_key"])
                mapping[action_key] = (
                    int(row["fold_count"]),
                    int(row["val_batches_per_fold"]),
                    int(row["train_batches_per_fold"]),
                )
            source_path = candidate_path
        elif allow_winner_fallback:
            fallback = _load_winner_fallback_candidate_map(
                project_root=project_root,
                run_id=run_id,
                model_name=model_name,
                unit=unit,
            )
            if fallback is not None:
                mapping, source_path = fallback
                print(f"[{unit}] candidate source fallback -> {source_path}")

        if mapping is None or source_path is None:
            raise FileNotFoundError(
                f"Missing candidate file for {unit}: {candidate_path}. "
                f"This candidate-search run likely does not include unit {unit}. "
                "Run candidate search for this unit, or use --candidate-fallback-from-winners "
                "if winner artifacts exist for the unit."
            )
        if len(mapping) != 12:
            raise ValueError(
                f"{unit} candidate set size must be 12, got {len(mapping)} ({source_path})"
            )
        out[unit] = dict(mapping)
    return out


def _build_expected_combos_from_candidate_map(
    candidate_map: dict[str, tuple[int, int, int]]
) -> list[dict[str, int]]:
    rows = sorted(
        {
            (int(tri[0]), int(tri[1]), int(tri[2]))
            for tri in candidate_map.values()
        }
    )
    return [
        {
            "fold_count": int(f),
            "val_batches_per_fold": int(v),
            "train_batches_per_fold": int(t),
        }
        for f, v, t in rows
    ]


def _run_preflight_diagnostic(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    units: list[str],
    candidate_map_by_unit: dict[str, dict[str, tuple[int, int, int]]],
) -> dict[str, Any]:
    strict_broken_reasons = {
        "missing_artifacts",
        "summary_unreadable",
        "invalid_combo_total",
        "zero_completed_combos",
    }
    units_summary: dict[str, Any] = {}
    total_steps = 0
    ok_steps = 0
    needs_migration_steps = 0
    grid_gap_steps = 0
    broken_steps = 0
    broken_examples: list[dict[str, Any]] = []
    started = time.perf_counter()

    for unit in units:
        tf, target = unit.split("/", 1)
        unit_dir = (
            project_root / "data" / "htf_backtest_results" / run_id / model_name / tf / target
        )
        batch_dirs = sorted(
            [p for p in unit_dir.glob("batch_*") if p.is_dir()],
            key=lambda p: int(p.name.split("_")[1]),
        )
        expected_combos = _build_expected_combos_from_candidate_map(
            candidate_map_by_unit[unit]
        )

        unit_reason_counts: dict[str, int] = {}
        unit_broken_examples: list[dict[str, Any]] = []
        unit_ok = 0
        unit_needs_migration = 0
        unit_grid_gap = 0
        unit_broken = 0

        for batch_dir in batch_dirs:
            pred_batch = int(batch_dir.name.split("_")[1])
            status = _stage1_step_artifact_status(
                step_dir=batch_dir,
                expected_combos=expected_combos,
            )
            reason = str(status.get("reason", "unknown"))
            unit_reason_counts[reason] = int(unit_reason_counts.get(reason, 0) + 1)
            if reason == "ok":
                unit_ok += 1
            elif reason == "ok_needs_grid_migration":
                unit_needs_migration += 1
            elif reason == "missing_expected_combos":
                unit_grid_gap += 1
            else:
                is_broken = (reason in strict_broken_reasons) or (
                    not bool(status.get("is_complete", False))
                    and reason not in {"missing_expected_combos"}
                )
                if is_broken:
                    unit_broken += 1
                    if len(unit_broken_examples) < 15:
                        unit_broken_examples.append(
                            {
                                "pred_batch": int(pred_batch),
                                "reason": reason,
                                "missing_artifacts": list(status.get("missing", []) or []),
                                "missing_expected_count": int(
                                    status.get("missing_expected_count", 0) or 0
                                ),
                            }
                        )

        unit_total = int(len(batch_dirs))
        units_summary[unit] = {
            "steps_total": unit_total,
            "ok_steps": int(unit_ok),
            "needs_migration_steps": int(unit_needs_migration),
            "grid_gap_steps": int(unit_grid_gap),
            "broken_steps": int(unit_broken),
            "reason_counts": unit_reason_counts,
            "broken_examples": unit_broken_examples,
        }
        print(
            f"[{unit}] preflight: total={unit_total} ok={unit_ok} "
            f"needs_migration={unit_needs_migration} grid_gap={unit_grid_gap} "
            f"broken={unit_broken}"
        )

        total_steps += unit_total
        ok_steps += int(unit_ok)
        needs_migration_steps += int(unit_needs_migration)
        grid_gap_steps += int(unit_grid_gap)
        broken_steps += int(unit_broken)
        for row in unit_broken_examples:
            if len(broken_examples) >= 30:
                break
            copy_row = dict(row)
            copy_row["unit"] = unit
            broken_examples.append(copy_row)

    return {
        "enabled": True,
        "runtime_s": float(time.perf_counter() - started),
        "totals": {
            "steps_total": int(total_steps),
            "ok_steps": int(ok_steps),
            "needs_migration_steps": int(needs_migration_steps),
            "grid_gap_steps": int(grid_gap_steps),
            "broken_steps": int(broken_steps),
        },
        "units": units_summary,
        "broken_examples": broken_examples,
    }


def _stage1_action_key_from_triplet(fold_count: int, val_batches: int, train_batches: int) -> str:
    return f"f{int(fold_count)}_v{int(val_batches)}_t{int(train_batches)}"


def _augment_candidate_map_with_proportional_f1(
    *,
    candidate_map_by_unit: dict[str, dict[str, tuple[int, int, int]]],
    max_extra_per_unit: int,
    include_fold_scaled: bool,
) -> tuple[dict[str, dict[str, tuple[int, int, int]]], dict[str, dict[str, Any]]]:
    if int(max_extra_per_unit) < 0:
        raise ValueError("max_extra_per_unit must be >= 0")

    out: dict[str, dict[str, tuple[int, int, int]]] = {}
    audit: dict[str, dict[str, Any]] = {}

    for unit, base_map in candidate_map_by_unit.items():
        merged = dict(base_map)
        vt_support: dict[tuple[int, int], int] = {}
        for _, tri in base_map.items():
            _, v, t = tri
            vt_support[(int(v), int(t))] = int(vt_support.get((int(v), int(t)), 0) + 1)

        candidates: list[tuple[str, tuple[int, int, int], int, int, int, int, str]] = []
        direct_generated = 0
        fold_scaled_generated = 0
        for action_key, tri in sorted(base_map.items()):
            f, v, t = int(tri[0]), int(tri[1]), int(tri[2])
            if f <= 1:
                continue
            f1_key = _stage1_action_key_from_triplet(1, v, t)
            support = int(vt_support.get((v, t), 1))
            candidates.append((f1_key, (1, v, t), support, v, t, 0, "direct"))
            direct_generated += 1
            if include_fold_scaled:
                scaled_v = max(1, int(f * v))
                scaled_t = max(1, int(f * t))
                scaled_key = _stage1_action_key_from_triplet(1, scaled_v, scaled_t)
                if scaled_key != f1_key:
                    candidates.append(
                        (
                            scaled_key,
                            (1, scaled_v, scaled_t),
                            support,
                            scaled_v,
                            scaled_t,
                            1,
                            "fold_scaled",
                        )
                    )
                    fold_scaled_generated += 1

        dedup: dict[str, tuple[tuple[int, int, int], int, int, int, int, str]] = {}
        for f1_key, tri, support, v, t, tier, source in candidates:
            existing = dedup.get(f1_key)
            if existing is None:
                dedup[f1_key] = (tri, support, v, t, tier, source)
            else:
                existing_support = int(existing[1])
                existing_tier = int(existing[4])
                if int(tier) < existing_tier:
                    dedup[f1_key] = (tri, support, v, t, tier, source)
                elif int(tier) == existing_tier:
                    dedup[f1_key] = (
                        tri,
                        max(existing_support, int(support)),
                        int(v),
                        int(t),
                        int(tier),
                        str(source),
                    )

        ranked = sorted(
            dedup.items(),
            key=lambda kv: (
                int(kv[1][4]),   # prefer direct projection before fold-scaled
                -int(kv[1][1]),  # then prefer val/train patterns repeated across folds
                int(kv[1][2]),   # deterministic ordering
                int(kv[1][3]),   # deterministic ordering
                str(kv[0]),
            ),
        )

        added_keys: list[str] = []
        skipped_existing = 0
        skipped_capacity = 0

        for f1_key, payload in ranked:
            tri = payload[0]
            if f1_key in merged:
                skipped_existing += 1
                continue
            if len(added_keys) >= int(max_extra_per_unit):
                skipped_capacity += 1
                continue
            merged[f1_key] = tri
            added_keys.append(str(f1_key))

        out[unit] = merged
        audit[unit] = {
            "base_candidate_count": int(len(base_map)),
            "derived_f1_direct_generated": int(direct_generated),
            "derived_f1_fold_scaled_generated": int(fold_scaled_generated),
            "derived_f1_candidates_total": int(len(ranked)),
            "derived_f1_candidates_added": int(len(added_keys)),
            "derived_f1_candidates_skipped_existing": int(skipped_existing),
            "derived_f1_candidates_skipped_capacity": int(max(0, len(ranked) - len(added_keys) - skipped_existing)),
            "final_candidate_count": int(len(merged)),
            "added_action_keys": added_keys,
        }

    return out, audit


def _count_unit_steps(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
) -> dict[str, Any]:
    tf, target = unit.split("/", 1)
    unit_dir = (
        project_root / "data" / "htf_backtest_results" / run_id / model_name / tf / target
    )
    if not unit_dir.exists():
        return {"steps_total": 0, "pred_batch_min": None, "pred_batch_max": None}
    batch_ids: list[int] = []
    for p in unit_dir.glob("batch_*"):
        if not p.is_dir():
            continue
        try:
            batch_ids.append(int(p.name.split("_")[1]))
        except Exception:
            continue
    if not batch_ids:
        return {"steps_total": 0, "pred_batch_min": None, "pred_batch_max": None}
    return {
        "steps_total": int(len(batch_ids)),
        "pred_batch_min": int(min(batch_ids)),
        "pred_batch_max": int(max(batch_ids)),
    }


def _build_stage1_tf_spec_from_candidates(
    *,
    tf: str,
    target_triplets: dict[str, list[tuple[int, int, int]]],
) -> dict[str, Any]:
    if tf not in STAGE1_LOOKBACK_MAX_BY_TF:
        raise ValueError(f"Unsupported timeframe: {tf}")
    all_triplets = [
        tri
        for rows in target_triplets.values()
        for tri in rows
    ]
    if all_triplets:
        max_train = max(int(t[2]) for t in all_triplets)
        max_folds = max(int(t[0]) for t in all_triplets)
        max_val = max(int(t[1]) for t in all_triplets)
        min_train = min(int(t[2]) for t in all_triplets)
        min_folds = min(int(t[0]) for t in all_triplets)
        min_val = min(int(t[1]) for t in all_triplets)
    else:
        max_train, max_folds, max_val = 36, 9, 4
        min_train, min_folds, min_val = 2, 2, 1
    lookback_min = max(100, max_train + max_folds * max_val + 2)
    lookback_max = int(STAGE1_LOOKBACK_MAX_BY_TF[tf])
    min_samples = int(STAGE1_MIN_SAMPLES_BY_TF[tf])

    shared_optuna = {
        "track_pred_metrics": False,
        "balance_strategy": "none",
        "balance_apply_to": "train",
        "cb_base_params": dict(STAGE1_CB_BASE_PARAMS),
        "window_space": {
            "lookback_min": int(lookback_min),
            "lookback_max": int(lookback_max),
            "window_selection_mode": "stage1_fold_cv",
            "stage1_execution_mode": "fast_grid",
            "stage1_folds_min": int(min_folds),
            "stage1_folds_max": int(max_folds),
            "stage1_val_batches_min": int(min_val),
            "stage1_val_batches_max": int(max_val),
            "stage1_train_batches_min": int(min_train),
            "stage1_train_batches_max": int(max_train),
            "stage1_stability_lambda": 0.25,
            "stage1_trial_selection_mode": "prediction_batch",
            "embargo_mode": "auto_tf",
        },
        "model_space": {"num_boost_round_min": 300, "num_boost_round_max": 300},
    }

    targets: dict[str, Any] = {}
    if "target_4class" in target_triplets:
        targets["target_4class"] = {
            "task_type": "multiclass",
            "n_classes": 4,
            "class_names": list(CLASS_NAMES_4),
            "feature_source": "target_4class",
            "optuna": {
                "optuna_metric": "cross_direction_error",
                "stage1_validity_target_col": "target_4class",
                "window_space": {
                    "min_samples_per_class": int(min_samples),
                    "stage1_triplet_grid": [list(t) for t in target_triplets["target_4class"]],
                },
            },
        }
    if "target_breakfree" in target_triplets:
        targets["target_breakfree"] = {
            "task_type": "multiclass",
            "n_classes": 3,
            "class_names": list(CLASS_NAMES_BREAKFREE),
            "feature_source": "target_4class",
            "optuna": {
                "optuna_metric": "macro_f1",
                "stage1_validity_target_col": "target_4class",
                "window_space": {
                    "min_samples_per_class": int(min_samples),
                    "stage1_triplet_grid": [
                        list(t) for t in target_triplets["target_breakfree"]
                    ],
                },
            },
        }
    if not targets:
        raise ValueError(f"No targets resolved for timeframe {tf}")

    return {"shared_optuna": shared_optuna, "targets": targets}


def _build_stage1_maps_from_candidate_grid(
    *,
    model_name: str,
    units: list[str],
    candidate_map_by_unit: dict[str, dict[str, tuple[int, int, int]]],
) -> dict[str, Any]:
    tf_targets: dict[str, dict[str, list[tuple[int, int, int]]]] = {}
    for unit in units:
        tf, target = unit.split("/", 1)
        if tf not in {"1m", "5m", "15m"}:
            raise ValueError(f"Unsupported timeframe in unit {unit!r}")
        if target not in {"target_4class", "target_breakfree"}:
            raise ValueError(f"Unsupported target in unit {unit!r}")
        rows = sorted(
            {
                (
                    int(tri[0]),
                    int(tri[1]),
                    int(tri[2]),
                )
                for tri in candidate_map_by_unit.get(unit, {}).values()
            }
        )
        if not rows:
            raise ValueError(f"No candidate triplets resolved for {unit}")
        tf_targets.setdefault(tf, {})[target] = rows

    model_specs = {
        str(model_name): {
            "timeframes": {
                tf: _build_stage1_tf_spec_from_candidates(
                    tf=tf,
                    target_triplets=targets,
                )
                for tf, targets in sorted(tf_targets.items())
            }
        }
    }
    return build_backtest_maps(model_specs)


def _ensure_stage1_steps_if_requested(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    units: list[str],
    candidate_map_by_unit: dict[str, dict[str, tuple[int, int, int]]],
    ensure_stage1_steps: int,
    ensure_stage1_resume_mode: str,
    ensure_stage1_debug_batches: bool,
    ensure_stage1_serial_units: bool,
    ensure_stage1_probe_enabled: bool,
    ensure_stage1_backfill_low_quality_completed: bool,
    verbose: bool,
) -> dict[str, Any]:
    if int(ensure_stage1_steps) <= 0:
        return {
            "enabled": False,
            "requested_n_steps": int(ensure_stage1_steps),
            "resume_mode": str(ensure_stage1_resume_mode),
            "serial_units": bool(ensure_stage1_serial_units),
            "probe_enabled": bool(ensure_stage1_probe_enabled),
            "backfill_low_quality_completed": bool(
                ensure_stage1_backfill_low_quality_completed
            ),
            "runner_invoked": False,
            "units_before": {
                unit: _count_unit_steps(
                    project_root=project_root,
                    run_id=run_id,
                    model_name=model_name,
                    unit=unit,
                )
                for unit in units
            },
            "units_after": {
                unit: _count_unit_steps(
                    project_root=project_root,
                    run_id=run_id,
                    model_name=model_name,
                    unit=unit,
                )
                for unit in units
            },
        }

    if str(model_name) != "catboost":
        raise ValueError(
            "Pre-backfill Stage-1 ensure mode currently supports only model_name='catboost'."
        )

    run_root = project_root / "data" / "htf_backtest_results" / run_id
    units_before = {
        unit: _count_unit_steps(
            project_root=project_root,
            run_id=run_id,
            model_name=model_name,
            unit=unit,
        )
        for unit in units
    }

    print("\nEnsuring Stage-1 step folders before backfill...")
    print(
        "  "
        f"requested_n_steps={int(ensure_stage1_steps)} "
        f"resume_mode={ensure_stage1_resume_mode} "
        f"serial_units={bool(ensure_stage1_serial_units)}"
    )

    runner_result_entries: list[dict[str, Any]] = []
    runner_t0 = time.perf_counter()
    ensure_units = list(units) if bool(ensure_stage1_serial_units) else [",".join(units)]
    for ensure_unit_key in ensure_units:
        unit_subset = (
            [ensure_unit_key] if bool(ensure_stage1_serial_units) else list(units)
        )
        maps = _build_stage1_maps_from_candidate_grid(
            model_name=model_name,
            units=unit_subset,
            candidate_map_by_unit=candidate_map_by_unit,
        )
        if bool(ensure_stage1_serial_units):
            print(
                f"  ensure_unit={unit_subset[0]} "
                f"timeframes={maps['timeframes_by_model'][model_name]}"
            )

        unit_runner_t0 = time.perf_counter()
        unit_runner_result = run_walk_forward_stage1_grid(
            n_steps=int(ensure_stage1_steps),
            timeframes=list(maps["timeframes_by_model"][model_name]),
            run_description="stage1_multiunit_candidate_backfill pre-backfill ensure",
            verbose=bool(verbose),
            debug_batches=bool(ensure_stage1_debug_batches),
            run_id=run_id,
            resume=bool(run_root.exists()),
            resume_mode=str(ensure_stage1_resume_mode),
            allow_override_mismatch=False,
            model_name=model_name,
            optuna_overrides_by_model=maps["optuna_overrides_by_model"],
            targets_by_model=maps["targets_by_model"],
            n_classes_by_model=maps["n_classes_by_model"],
            class_names_by_model=maps["class_names_by_model"],
            feature_source_by_model=maps["feature_source_by_model"],
            target_registry=maps["target_registry"],
            stage1_quality_accuracy_threshold=0.70,
            stage1_probe_enabled=bool(ensure_stage1_probe_enabled),
            stage1_probe_tier_sizes=[8, 8, 8, 8],
            stage1_probe_max_extra_candidates=32,
            stage1_probe_source_scope="current+archive",
            stage1_backfill_low_quality_completed=bool(
                ensure_stage1_backfill_low_quality_completed
            ),
            stage1_promotion_mode="global",
            stage1_promoted_combo_cap_per_unit=8,
        )
        unit_runtime_s = float(time.perf_counter() - unit_runner_t0)
        runner_result_entries.append(
            {
                "units": list(unit_subset),
                "runtime_s": unit_runtime_s,
                "n_steps": int(unit_runner_result.get("n_steps", 0) or 0),
                "step_batches_count": int(len(unit_runner_result.get("step_batches", []) or [])),
                "step_batch_min": (
                    int(min(unit_runner_result.get("step_batches", [])))
                    if unit_runner_result.get("step_batches")
                    else None
                ),
                "step_batch_max": (
                    int(max(unit_runner_result.get("step_batches", [])))
                    if unit_runner_result.get("step_batches")
                    else None
                ),
                "timeframes": list(unit_runner_result.get("timeframes", []) or []),
            }
        )

    runner_runtime_s = float(time.perf_counter() - runner_t0)
    units_after = {
        unit: _count_unit_steps(
            project_root=project_root,
            run_id=run_id,
            model_name=model_name,
            unit=unit,
        )
        for unit in units
    }
    for unit in units:
        before_steps = int(units_before[unit]["steps_total"])
        after_steps = int(units_after[unit]["steps_total"])
        print(f"  [{unit}] steps_before={before_steps} steps_after={after_steps}")

    return {
        "enabled": True,
        "requested_n_steps": int(ensure_stage1_steps),
        "resume_mode": str(ensure_stage1_resume_mode),
        "serial_units": bool(ensure_stage1_serial_units),
        "probe_enabled": bool(ensure_stage1_probe_enabled),
        "backfill_low_quality_completed": bool(
            ensure_stage1_backfill_low_quality_completed
        ),
        "runner_invoked": True,
        "runner_runtime_s": runner_runtime_s,
        "runner_result_entries": runner_result_entries,
        "units_before": units_before,
        "units_after": units_after,
    }


def _write_df_pair(df: pl.DataFrame, parquet_path: Path, csv_path: Path) -> None:
    df.write_parquet(parquet_path)
    df.write_csv(csv_path)


def _backfill_unit(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    candidate_map: dict[str, tuple[int, int, int]],
    source_scope: str,
    apply: bool,
    candidate_source: str,
    discovered_from: str,
    max_steps_per_unit: int,
    progress_every_steps: int,
    verbose: bool,
    output_dir: Path,
) -> dict[str, Any]:
    tf, target = unit.split("/", 1)
    unit_dir = (
        project_root / "data" / "htf_backtest_results" / run_id / model_name / tf / target
    )
    if not unit_dir.exists():
        raise FileNotFoundError(f"Unit dir not found: {unit_dir}")

    required_action_keys = sorted(candidate_map.keys())
    coverage_before_df, missing_before_df = _scan_candidate_coverage(
        unit_dir=unit_dir,
        required_action_keys=required_action_keys,
        scope=source_scope,
    )
    before_full_coverage_steps = (
        int((coverage_before_df["missing_count"] == 0).sum()) if not coverage_before_df.is_empty() else 0
    )
    before_missing_steps = (
        int((coverage_before_df["missing_count"] > 0).sum()) if not coverage_before_df.is_empty() else 0
    )
    before_missing_pairs = int(len(missing_before_df))
    print(
        f"[{unit}] coverage_before: full_coverage_steps={before_full_coverage_steps}/{len(coverage_before_df)} "
        f"missing_steps={before_missing_steps} missing_pairs={before_missing_pairs}"
    )

    step_rows: list[dict[str, Any]] = []
    backfill_t0 = time.perf_counter()
    steps_ok = 0
    steps_error = 0

    if apply and not missing_before_df.is_empty():
        missing_by_step = (
            missing_before_df.group_by("pred_batch")
            .agg(pl.col("action_key").sort().alias("missing_action_keys"))
            .sort("pred_batch")
        )
        if max_steps_per_unit > 0:
            missing_by_step = missing_by_step.head(int(max_steps_per_unit))
        total_steps = int(len(missing_by_step))
        total_pairs = int(missing_by_step["missing_action_keys"].list.len().sum())
        print(
            f"[{unit}] backfill_plan: steps_to_process={total_steps} "
            f"missing_pairs_to_process={total_pairs}"
        )

        for i, row in enumerate(missing_by_step.iter_rows(named=True), start=1):
            pred_batch = int(row["pred_batch"])
            train_end = int(pred_batch - 1)
            missing_keys = [str(v) for v in list(row["missing_action_keys"] or []) if str(v)]
            step_stage1_dir = unit_dir / f"batch_{pred_batch:04d}" / "stage1"
            step_snapshot_path = step_stage1_dir / "stage1_config_snapshot.json"
            step_summary_path = step_stage1_dir / "stage1_step_summary.json"

            if verbose:
                print(
                    f"[{unit}] step {i}/{total_steps} pred_batch={pred_batch} "
                    f"train_end={train_end} missing={missing_keys}"
                )

            if not step_snapshot_path.exists():
                step_rows.append(
                    {
                        "pred_batch": pred_batch,
                        "train_end": train_end,
                        "status": "error",
                        "error": f"missing_snapshot:{step_snapshot_path}",
                        "missing_action_keys": json.dumps(missing_keys),
                        "combos_requested": len(missing_keys),
                        "combos_evaluated": 0,
                        "combo_count_new_this_run": 0,
                        "winner_before_key": None,
                        "winner_before_accuracy": None,
                        "winner_after_key": None,
                        "winner_after_accuracy": None,
                        "quality_pass_after": None,
                        "runtime_s": None,
                    }
                )
                continue

            try:
                cfg, step_optimizer = _load_step_optimizer_from_snapshot(
                    tf=tf,
                    snapshot_path=step_snapshot_path,
                )
            except Exception as exc:
                step_rows.append(
                    {
                        "pred_batch": pred_batch,
                        "train_end": train_end,
                        "status": "error",
                        "error": f"snapshot_load_error:{exc}",
                        "missing_action_keys": json.dumps(missing_keys),
                        "combos_requested": len(missing_keys),
                        "combos_evaluated": 0,
                        "combo_count_new_this_run": 0,
                        "winner_before_key": None,
                        "winner_before_accuracy": None,
                        "winner_after_key": None,
                        "winner_after_accuracy": None,
                        "quality_pass_after": None,
                        "runtime_s": None,
                    }
                )
                continue

            combo_override = []
            for action_key in missing_keys:
                tri = candidate_map.get(action_key)
                if tri is None:
                    continue
                combo_override.append(
                    {
                        "fold_count": int(tri[0]),
                        "val_batches_per_fold": int(tri[1]),
                        "train_batches_per_fold": int(tri[2]),
                        "action_key": str(action_key),
                    }
                )
            if not combo_override:
                step_rows.append(
                    {
                        "pred_batch": pred_batch,
                        "train_end": train_end,
                        "status": "error",
                        "error": "no_valid_missing_combos",
                        "missing_action_keys": json.dumps(missing_keys),
                        "combos_requested": len(missing_keys),
                        "combos_evaluated": 0,
                        "combo_count_new_this_run": 0,
                        "winner_before_key": None,
                        "winner_before_accuracy": None,
                        "winner_after_key": None,
                        "winner_after_accuracy": None,
                        "quality_pass_after": None,
                        "runtime_s": None,
                    }
                )
                continue

            winner_before = _stage1_get_step_winner_metrics(
                stage1_dir=step_stage1_dir,
                n_classes=int(cfg.n_classes),
                class_names=list(cfg.class_names),
            )
            winner_before_key = str(winner_before.get("action_key")) if winner_before else None
            winner_before_acc = (
                float(winner_before.get("accuracy"))
                if winner_before and winner_before.get("accuracy") is not None
                else None
            )

            t0 = time.perf_counter()
            try:
                eval_result = evaluate_stage1_grid(
                    step_optimizer=step_optimizer,
                    train_end=train_end,
                    pred_batch=pred_batch,
                    step_stage1_dir=step_stage1_dir,
                    combo_grid_override=combo_override,
                    append_mode=True,
                    candidate_source=candidate_source,
                    probe_tier=-1,
                    discovered_from=discovered_from,
                )
                runtime_s = float(time.perf_counter() - t0)

                winner_after = _stage1_get_step_winner_metrics(
                    stage1_dir=step_stage1_dir,
                    n_classes=int(cfg.n_classes),
                    class_names=list(cfg.class_names),
                )
                winner_after_key = str(winner_after.get("action_key")) if winner_after else None
                winner_after_acc = (
                    float(winner_after.get("accuracy"))
                    if winner_after and winner_after.get("accuracy") is not None
                    else None
                )

                existing_summary = {}
                if step_summary_path.exists():
                    with open(step_summary_path, encoding="utf-8") as f:
                        existing_summary = json.load(f)
                quality_threshold = float(existing_summary.get("quality_threshold", 0.70) or 0.70)
                quality_unresolved = bool(existing_summary.get("quality_unresolved", False))
                probe_exhausted = bool(existing_summary.get("probe_exhausted", False))
                if winner_after_acc is not None and winner_after_acc >= quality_threshold:
                    quality_unresolved = False
                    probe_exhausted = False

                updated_summary = _stage1_update_step_summary_quality(
                    stage1_dir=step_stage1_dir,
                    quality_threshold=quality_threshold,
                    winner=winner_after,
                    quality_unresolved=quality_unresolved,
                    probe_exhausted=probe_exhausted,
                    probe_enabled=bool(existing_summary.get("probe_enabled", False)),
                    probe_tiers_run=int(existing_summary.get("probe_tiers_run", 0) or 0),
                    probe_candidates_evaluated=int(
                        existing_summary.get("probe_candidates_evaluated", 0) or 0
                    ),
                )

                combo_count_new = int(eval_result["summary"].get("combo_count_new_this_run", 0) or 0)
                quality_pass_after = bool(updated_summary.get("quality_pass", False))
                step_rows.append(
                    {
                        "pred_batch": pred_batch,
                        "train_end": train_end,
                        "status": "ok",
                        "error": None,
                        "missing_action_keys": json.dumps(missing_keys),
                        "combos_requested": len(missing_keys),
                        "combos_evaluated": len(combo_override),
                        "combo_count_new_this_run": combo_count_new,
                        "winner_before_key": winner_before_key,
                        "winner_before_accuracy": winner_before_acc,
                        "winner_after_key": winner_after_key,
                        "winner_after_accuracy": winner_after_acc,
                        "quality_pass_after": quality_pass_after,
                        "runtime_s": runtime_s,
                    }
                )
            except Exception as exc:
                runtime_s = float(time.perf_counter() - t0)
                step_rows.append(
                    {
                        "pred_batch": pred_batch,
                        "train_end": train_end,
                        "status": "error",
                        "error": str(exc),
                        "missing_action_keys": json.dumps(missing_keys),
                        "combos_requested": len(missing_keys),
                        "combos_evaluated": len(combo_override),
                        "combo_count_new_this_run": 0,
                        "winner_before_key": winner_before_key,
                        "winner_before_accuracy": winner_before_acc,
                        "winner_after_key": None,
                        "winner_after_accuracy": None,
                        "quality_pass_after": None,
                        "runtime_s": runtime_s,
                    }
                )
                if verbose:
                    print(f"[{unit}] ERROR pred_batch={pred_batch}: {exc}")

            # Progress heartbeat (always prints on first/last; optional cadence in-between).
            if step_rows:
                last_status = str(step_rows[-1].get("status"))
                if last_status == "ok":
                    steps_ok += 1
                elif last_status == "error":
                    steps_error += 1
                cadence_hit = progress_every_steps > 0 and (i % int(progress_every_steps) == 0)
                if verbose or i == 1 or i == total_steps or cadence_hit:
                    elapsed = float(time.perf_counter() - backfill_t0)
                    avg_per_step = elapsed / float(i) if i > 0 else 0.0
                    eta = avg_per_step * float(max(0, total_steps - i))
                    print(
                        f"[{unit}] progress {i}/{total_steps} "
                        f"ok={steps_ok} error={steps_error} "
                        f"elapsed={elapsed:.1f}s eta={eta:.1f}s "
                        f"last_pred_batch={pred_batch} last_status={last_status}"
                    )
    elif apply:
        print(f"[{unit}] no missing pairs; nothing to backfill.")
    else:
        print(f"[{unit}] audit-only mode (apply=False).")

    backfill_runtime_s = float(time.perf_counter() - backfill_t0)

    coverage_after_df, missing_after_df = _scan_candidate_coverage(
        unit_dir=unit_dir,
        required_action_keys=required_action_keys,
        scope=source_scope,
    )
    after_full_coverage_steps = (
        int((coverage_after_df["missing_count"] == 0).sum()) if not coverage_after_df.is_empty() else 0
    )
    after_missing_steps = (
        int((coverage_after_df["missing_count"] > 0).sum()) if not coverage_after_df.is_empty() else 0
    )
    after_missing_pairs = int(len(missing_after_df))
    print(
        f"[{unit}] coverage_after: full_coverage_steps={after_full_coverage_steps}/{len(coverage_after_df)} "
        f"missing_steps={after_missing_steps} missing_pairs={after_missing_pairs} "
        f"runtime_s={backfill_runtime_s:.1f}"
    )

    unit_out_dir = output_dir / tf / target
    unit_out_dir.mkdir(parents=True, exist_ok=True)
    coverage_before_parquet = unit_out_dir / "coverage_before.parquet"
    coverage_before_csv = unit_out_dir / "coverage_before.csv"
    missing_before_parquet = unit_out_dir / "missing_pairs_before.parquet"
    missing_before_csv = unit_out_dir / "missing_pairs_before.csv"
    backfill_steps_parquet = unit_out_dir / "backfill_step_results.parquet"
    backfill_steps_csv = unit_out_dir / "backfill_step_results.csv"
    coverage_after_parquet = unit_out_dir / "coverage_after.parquet"
    coverage_after_csv = unit_out_dir / "coverage_after.csv"
    missing_after_parquet = unit_out_dir / "missing_pairs_after.parquet"
    missing_after_csv = unit_out_dir / "missing_pairs_after.csv"
    summary_json = unit_out_dir / "backfill_summary.json"

    step_df = (
        pl.DataFrame(step_rows)
        if step_rows
        else pl.DataFrame(
            schema={
                "pred_batch": pl.Int64,
                "train_end": pl.Int64,
                "status": pl.Utf8,
                "error": pl.Utf8,
                "missing_action_keys": pl.Utf8,
                "combos_requested": pl.Int64,
                "combos_evaluated": pl.Int64,
                "combo_count_new_this_run": pl.Int64,
                "winner_before_key": pl.Utf8,
                "winner_before_accuracy": pl.Float64,
                "winner_after_key": pl.Utf8,
                "winner_after_accuracy": pl.Float64,
                "quality_pass_after": pl.Boolean,
                "runtime_s": pl.Float64,
            }
        )
    )
    if not step_df.is_empty():
        step_df = step_df.sort("pred_batch")

    _write_df_pair(coverage_before_df, coverage_before_parquet, coverage_before_csv)
    _write_df_pair(missing_before_df, missing_before_parquet, missing_before_csv)
    _write_df_pair(step_df, backfill_steps_parquet, backfill_steps_csv)
    _write_df_pair(coverage_after_df, coverage_after_parquet, coverage_after_csv)
    _write_df_pair(missing_after_df, missing_after_parquet, missing_after_csv)

    summary = {
        "unit": unit,
        "run_id": run_id,
        "model_name": model_name,
        "source_scope": source_scope,
        "apply": bool(apply),
        "max_steps_per_unit": int(max_steps_per_unit),
        "candidate_count": int(len(required_action_keys)),
        "before": {
            "steps_total": int(len(coverage_before_df)),
            "full_coverage_steps": int(before_full_coverage_steps),
            "full12_steps": int(before_full_coverage_steps),  # backward compatibility
            "missing_steps": int(before_missing_steps),
            "missing_pairs": int(before_missing_pairs),
        },
        "after": {
            "steps_total": int(len(coverage_after_df)),
            "full_coverage_steps": int(after_full_coverage_steps),
            "full12_steps": int(after_full_coverage_steps),  # backward compatibility
            "missing_steps": int(after_missing_steps),
            "missing_pairs": int(after_missing_pairs),
        },
        "backfill": {
            "steps_attempted": int(len(step_df)),
            "steps_ok": int((step_df["status"] == "ok").sum()) if not step_df.is_empty() else 0,
            "steps_error": int((step_df["status"] == "error").sum()) if not step_df.is_empty() else 0,
            "runtime_s": backfill_runtime_s,
        },
        "artifacts": {
            "coverage_before_parquet": str(coverage_before_parquet),
            "coverage_before_csv": str(coverage_before_csv),
            "missing_pairs_before_parquet": str(missing_before_parquet),
            "missing_pairs_before_csv": str(missing_before_csv),
            "backfill_step_results_parquet": str(backfill_steps_parquet),
            "backfill_step_results_csv": str(backfill_steps_csv),
            "coverage_after_parquet": str(coverage_after_parquet),
            "coverage_after_csv": str(coverage_after_csv),
            "missing_pairs_after_parquet": str(missing_after_parquet),
            "missing_pairs_after_csv": str(missing_after_csv),
            "summary_json": str(summary_json),
        },
    }
    _write_json(summary_json, summary)
    return summary


def _rerun_candidate_search(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    units: list[str],
    source_scope: str,
    output_tag: str,
) -> int:
    script_path = project_root / "htf_stage1" / "stage1_multiunit_candidate_search.py"
    cmd = [
        sys.executable,
        str(script_path),
        "--project-root",
        str(project_root),
        "--run-id",
        str(run_id),
        "--model-name",
        str(model_name),
        "--source-scope",
        str(source_scope),
        "--output-tag",
        str(output_tag),
    ]
    if units:
        cmd += ["--units", *units]
    print("\nRe-running candidate search after backfill...")
    print("  " + " ".join(cmd))
    proc = subprocess.run(cmd)
    return int(proc.returncode)


def main() -> None:
    args = _parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    run_id = str(args.run_id)
    model_name = str(args.model_name)
    source_scope = str(args.source_scope)
    units = _normalize_units(list(args.units))
    preflight_diagnostic = bool(args.preflight_diagnostic)
    preflight_fail_on_broken = bool(args.preflight_fail_on_broken)
    preflight_auto_fix_broken = bool(args.preflight_auto_fix_broken)
    apply = bool(args.apply)
    max_steps_per_unit = int(args.max_steps_per_unit)
    progress_every_steps = int(args.progress_every_steps)
    ensure_stage1_steps = int(args.ensure_stage1_steps)
    ensure_stage1_resume_mode = str(args.ensure_stage1_resume_mode)
    ensure_stage1_debug_batches = bool(args.ensure_stage1_debug_batches)
    ensure_stage1_serial_units = bool(args.ensure_stage1_serial_units)
    ensure_stage1_probe_enabled = bool(args.ensure_stage1_probe_enabled)
    ensure_stage1_backfill_low_quality_completed = bool(
        args.ensure_stage1_backfill_low_quality_completed
    )
    verbose = bool(args.verbose)

    candidate_run_dir = _resolve_candidate_run_dir(
        project_root=project_root,
        run_id=run_id,
        model_name=model_name,
        candidate_run_dir_arg=str(args.candidate_run_dir),
    )
    candidate_map_by_unit = _load_candidate_map(
        candidate_run_dir,
        units,
        project_root=project_root,
        run_id=run_id,
        model_name=model_name,
        allow_winner_fallback=bool(args.candidate_fallback_from_winners),
    )
    candidate_augmentation: dict[str, dict[str, Any]] = {}
    if bool(args.augment_proportional_f1):
        candidate_map_by_unit, candidate_augmentation = _augment_candidate_map_with_proportional_f1(
            candidate_map_by_unit=candidate_map_by_unit,
            max_extra_per_unit=int(args.f1_max_extra_per_unit),
            include_fold_scaled=bool(args.f1_augment_include_fold_scaled),
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = str(args.output_tag).strip().replace(" ", "_")
    run_name = f"run_{stamp}" + (f"_{tag}" if tag else "")
    out_root = (
        project_root
        / "data"
        / "htf_backtest_results"
        / run_id
        / model_name
        / "candidate_backfill_v2"
        / run_name
    )
    out_root.mkdir(parents=True, exist_ok=False)

    print("Stage-1 multi-unit candidate backfill (v2)")
    print(f"  Project root: {project_root}")
    print(f"  Run/model: {run_id}/{model_name}")
    print(f"  Units ({len(units)}): {units}")
    print(f"  Coverage scope: {source_scope}")
    print(f"  Candidate source run: {candidate_run_dir}")
    print(
        "  Preflight diagnostic: "
        f"enabled={preflight_diagnostic} fail_on_broken={preflight_fail_on_broken} "
        f"auto_fix_broken={preflight_auto_fix_broken}"
    )
    print(
        "  Ensure stage1 steps: "
        f"n_steps={ensure_stage1_steps} "
        f"(resume_mode={ensure_stage1_resume_mode}, "
        f"debug_batches={ensure_stage1_debug_batches}, "
        f"serial_units={ensure_stage1_serial_units}, "
        f"probe_enabled={ensure_stage1_probe_enabled}, "
        f"backfill_low_quality_completed={ensure_stage1_backfill_low_quality_completed})"
    )
    print(
        "  Proportional f1 augmentation: "
        f"{bool(args.augment_proportional_f1)} "
        f"(max_extra_per_unit={int(args.f1_max_extra_per_unit)}, "
        f"include_fold_scaled={bool(args.f1_augment_include_fold_scaled)})"
    )
    print(f"  Apply mode: {apply}")
    print(f"  Max steps per unit: {max_steps_per_unit}")
    print(f"  Output run dir: {out_root}")

    if candidate_augmentation:
        print("  Candidate counts after augmentation:")
        for unit in units:
            row = candidate_augmentation.get(unit, {})
            print(
                f"    {unit}: base={row.get('base_candidate_count', 0)} "
                f"added_f1={row.get('derived_f1_candidates_added', 0)} "
                f"final={row.get('final_candidate_count', 0)}"
            )

    preflight_summary = {
        "enabled": False,
        "totals": {
            "steps_total": 0,
            "ok_steps": 0,
            "needs_migration_steps": 0,
            "grid_gap_steps": 0,
            "broken_steps": 0,
        },
    }
    if preflight_diagnostic:
        print("\nRunning preflight diagnostic...")
        preflight_summary = _run_preflight_diagnostic(
            project_root=project_root,
            run_id=run_id,
            model_name=model_name,
            units=units,
            candidate_map_by_unit=candidate_map_by_unit,
        )
        print(
            "  Preflight totals: "
            f"total={preflight_summary['totals']['steps_total']} "
            f"ok={preflight_summary['totals']['ok_steps']} "
            f"needs_migration={preflight_summary['totals']['needs_migration_steps']} "
            f"grid_gap={preflight_summary['totals'].get('grid_gap_steps', 0)} "
            f"broken={preflight_summary['totals']['broken_steps']}"
        )
    preflight_summary_json = out_root / "preflight_diagnostic_summary.json"
    _write_json(preflight_summary_json, preflight_summary)
    preflight_autofix_summary: dict[str, Any] = {
        "enabled": bool(preflight_auto_fix_broken),
        "triggered": False,
        "broken_steps_detected": int(preflight_summary["totals"]["broken_steps"]),
        "ensure_steps_before": int(ensure_stage1_steps),
        "ensure_steps_after": int(ensure_stage1_steps),
        "strategy": "none",
        "note": "",
    }
    if preflight_auto_fix_broken and int(preflight_summary["totals"]["broken_steps"]) > 0:
        preflight_autofix_summary["triggered"] = True
        if int(ensure_stage1_steps) <= 0:
            inferred_steps = int(
                max(
                    [
                        int(v.get("steps_total", 0) or 0)
                        for v in (preflight_summary.get("units", {}) or {}).values()
                    ]
                    or [0]
                )
            )
            ensure_stage1_steps = int(inferred_steps)
            preflight_autofix_summary["strategy"] = "auto_infer_ensure_steps_from_preflight"
            preflight_autofix_summary["note"] = (
                "Auto-fix enabled and ensure n_steps was 0; using inferred discovered-step "
                "count to force Stage-1 rebuild pass."
            )
        else:
            preflight_autofix_summary["strategy"] = "use_requested_ensure_steps"
            preflight_autofix_summary["note"] = (
                "Auto-fix enabled; continuing into Stage-1 ensure/rebuild with requested n_steps."
            )
        preflight_autofix_summary["ensure_steps_after"] = int(ensure_stage1_steps)
        print(
            "\nPreflight auto-fix: broken steps detected, continuing with Stage-1 ensure/rebuild."
        )
        print(
            f"  ensure_stage1_steps before={preflight_autofix_summary['ensure_steps_before']} "
            f"after={preflight_autofix_summary['ensure_steps_after']}"
        )

    if (
        preflight_fail_on_broken
        and int(preflight_summary["totals"]["broken_steps"]) > 0
        and not preflight_auto_fix_broken
    ):
        print(
            "\nPreflight failed: broken steps detected and --preflight-fail-on-broken is set."
        )
        print(f"  Diagnostic: {preflight_summary_json}")
        raise SystemExit(2)
    preflight_autofix_summary_json = out_root / "preflight_autofix_summary.json"
    _write_json(preflight_autofix_summary_json, preflight_autofix_summary)

    ensure_summary = _ensure_stage1_steps_if_requested(
        project_root=project_root,
        run_id=run_id,
        model_name=model_name,
        units=units,
        candidate_map_by_unit=candidate_map_by_unit,
        ensure_stage1_steps=ensure_stage1_steps,
        ensure_stage1_resume_mode=ensure_stage1_resume_mode,
        ensure_stage1_debug_batches=ensure_stage1_debug_batches,
        ensure_stage1_serial_units=ensure_stage1_serial_units,
        ensure_stage1_probe_enabled=ensure_stage1_probe_enabled,
        ensure_stage1_backfill_low_quality_completed=ensure_stage1_backfill_low_quality_completed,
        verbose=verbose,
    )
    ensure_summary_json = out_root / "ensure_stage1_summary.json"
    _write_json(ensure_summary_json, ensure_summary)

    run_rows: list[dict[str, Any]] = []
    run_summary_units: dict[str, Any] = {}

    for unit in units:
        print(f"\n[{unit}] auditing/backfilling...")
        unit_summary = _backfill_unit(
            project_root=project_root,
            run_id=run_id,
            model_name=model_name,
            unit=unit,
            candidate_map=candidate_map_by_unit[unit],
            source_scope=source_scope,
            apply=apply,
            candidate_source=str(args.candidate_source),
            discovered_from=str(args.discovered_from),
            max_steps_per_unit=max_steps_per_unit,
            progress_every_steps=progress_every_steps,
            verbose=verbose,
            output_dir=out_root,
        )
        run_summary_units[unit] = unit_summary
        run_rows.append(
            {
                "unit": unit,
                "candidate_count": int(unit_summary["candidate_count"]),
                "before_full_coverage_steps": int(unit_summary["before"]["full_coverage_steps"]),
                "after_full_coverage_steps": int(unit_summary["after"]["full_coverage_steps"]),
                "before_full12_steps": int(unit_summary["before"]["full12_steps"]),
                "after_full12_steps": int(unit_summary["after"]["full12_steps"]),
                "before_missing_pairs": int(unit_summary["before"]["missing_pairs"]),
                "after_missing_pairs": int(unit_summary["after"]["missing_pairs"]),
                "steps_attempted": int(unit_summary["backfill"]["steps_attempted"]),
                "steps_ok": int(unit_summary["backfill"]["steps_ok"]),
                "steps_error": int(unit_summary["backfill"]["steps_error"]),
                "apply": bool(unit_summary["apply"]),
            }
        )
        print(
            f"[{unit}] candidate_count={unit_summary['candidate_count']} "
            f"before_missing_pairs={unit_summary['before']['missing_pairs']} "
            f"after_missing_pairs={unit_summary['after']['missing_pairs']} "
            f"steps_ok={unit_summary['backfill']['steps_ok']}/"
            f"{unit_summary['backfill']['steps_attempted']}"
        )

    run_table_df = pl.DataFrame(run_rows).sort("unit")
    run_table_parquet = out_root / "backfill_run_table_v2.parquet"
    run_table_csv = out_root / "backfill_run_table_v2.csv"
    run_table_df.write_parquet(run_table_parquet)
    run_table_df.write_csv(run_table_csv)

    resolved_candidates_by_unit = {
        unit: [
            {
                "action_key": str(action_key),
                "fold_count": int(tri[0]),
                "val_batches_per_fold": int(tri[1]),
                "train_batches_per_fold": int(tri[2]),
            }
            for action_key, tri in sorted(candidate_map_by_unit[unit].items())
        ]
        for unit in units
    }
    resolved_candidates_json = out_root / "resolved_candidates_by_unit.json"
    _write_json(resolved_candidates_json, resolved_candidates_by_unit)

    candidate_augmentation_json = out_root / "candidate_augmentation_summary.json"
    _write_json(
        candidate_augmentation_json,
        {
            "enabled": bool(args.augment_proportional_f1),
            "max_extra_per_unit": int(args.f1_max_extra_per_unit),
            "units": candidate_augmentation,
        },
    )

    rerun_exit_code = None
    rerun_output_tag = ""
    if bool(args.rerun_candidate_search):
        rerun_output_tag = f"post_backfill_{stamp}"
        rerun_exit_code = _rerun_candidate_search(
            project_root=project_root,
            run_id=run_id,
            model_name=model_name,
            units=units,
            source_scope=source_scope,
            output_tag=rerun_output_tag,
        )

    run_summary = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "run_id": run_id,
        "model_name": model_name,
        "source_scope": source_scope,
        "apply": bool(apply),
        "max_steps_per_unit": int(max_steps_per_unit),
        "preflight_diagnostic": bool(preflight_diagnostic),
        "preflight_fail_on_broken": bool(preflight_fail_on_broken),
        "preflight_auto_fix_broken": bool(preflight_auto_fix_broken),
        "ensure_stage1_steps": int(ensure_stage1_steps),
        "ensure_stage1_resume_mode": str(ensure_stage1_resume_mode),
        "ensure_stage1_debug_batches": bool(ensure_stage1_debug_batches),
        "ensure_stage1_serial_units": bool(ensure_stage1_serial_units),
        "ensure_stage1_probe_enabled": bool(ensure_stage1_probe_enabled),
        "ensure_stage1_backfill_low_quality_completed": bool(
            ensure_stage1_backfill_low_quality_completed
        ),
        "units": units,
        "candidate_run_dir": str(candidate_run_dir),
        "preflight_summary": preflight_summary,
        "preflight_autofix_summary": preflight_autofix_summary,
        "ensure_stage1_summary": ensure_summary,
        "proportional_f1_augmentation": {
            "enabled": bool(args.augment_proportional_f1),
            "max_extra_per_unit": int(args.f1_max_extra_per_unit),
            "units": candidate_augmentation,
        },
        "unit_summaries": run_summary_units,
        "candidate_search_rerun": {
            "enabled": bool(args.rerun_candidate_search),
            "output_tag": rerun_output_tag,
            "exit_code": rerun_exit_code,
        },
        "artifacts": {
            "backfill_run_table_v2_parquet": str(run_table_parquet),
            "backfill_run_table_v2_csv": str(run_table_csv),
            "resolved_candidates_by_unit_json": str(resolved_candidates_json),
            "candidate_augmentation_summary_json": str(candidate_augmentation_json),
            "preflight_diagnostic_summary_json": str(preflight_summary_json),
            "preflight_autofix_summary_json": str(preflight_autofix_summary_json),
            "ensure_stage1_summary_json": str(ensure_summary_json),
        },
    }
    run_summary_json = out_root / "backfill_run_summary_v2.json"
    _write_json(run_summary_json, run_summary)

    print("\nCompleted backfill run.")
    print(f"  Run table: {run_table_parquet}")
    print(f"  Run summary: {run_summary_json}")
    if rerun_exit_code is not None:
        print(f"  Candidate-search rerun exit_code={rerun_exit_code}")


if __name__ == "__main__":
    main()
