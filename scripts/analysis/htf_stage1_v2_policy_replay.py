from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.htf_backtest.catboost.stage1_feature_policy import (  # noqa: E402
    Stage1V2FixedPolicyConfig,
    build_stage1_v2_feature_policy,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a Stage-1-v2 fixed-policy registry from completed nested-selector "
            "artifacts. Replay execution will be added in a later slice."
        )
    )
    parser.add_argument(
        "--run-id",
        type=str,
        help="Stage-1 run id under data/htf_backtest_results/.",
    )
    parser.add_argument(
        "--run-path",
        type=str,
        help="Absolute or relative path to a Stage-1 run directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional output directory. Default: write registry and details into the run dir.",
    )
    parser.add_argument(
        "--policy-version",
        type=str,
        default=None,
        help="Optional explicit policy version label.",
    )
    parser.add_argument(
        "--support-min-selected-steps",
        type=int,
        default=40,
        help="Minimum selected-step support to classify core/avoid features.",
    )
    parser.add_argument(
        "--support-min-improved-steps",
        type=int,
        default=10,
        help="Minimum selected improved-step support for conditional features.",
    )
    parser.add_argument(
        "--core-selection-rate-min",
        type=float,
        default=0.80,
        help="Minimum within-combo selection rate for core features.",
    )
    parser.add_argument(
        "--conditional-improved-selection-lift-min",
        type=float,
        default=0.10,
        help="Minimum improved-vs-non-improved selection lift for conditional features.",
    )
    parser.add_argument(
        "--avoid-selection-rate-min",
        type=float,
        default=0.80,
        help="Minimum within-combo selection rate for avoid features.",
    )
    parser.add_argument(
        "--min-features-keep",
        type=int,
        default=24,
        help="Minimum final mask size per combo.",
    )
    parser.add_argument(
        "--max-features-keep",
        type=int,
        default=None,
        help="Optional maximum final mask size per combo.",
    )
    parser.add_argument(
        "--refresh-stride-steps",
        type=int,
        default=25,
        help="Planned live-safe policy refresh stride stored in the registry metadata.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if bool(args.run_id) == bool(args.run_path):
        raise SystemExit("Exactly one of --run-id or --run-path must be provided.")

    run_id_or_path = args.run_id or args.run_path
    cfg = Stage1V2FixedPolicyConfig(
        support_min_selected_steps=int(args.support_min_selected_steps),
        support_min_improved_steps=int(args.support_min_improved_steps),
        core_selection_rate_min=float(args.core_selection_rate_min),
        conditional_improved_selection_lift_min=float(
            args.conditional_improved_selection_lift_min
        ),
        avoid_selection_rate_min=float(args.avoid_selection_rate_min),
        min_features_keep=int(args.min_features_keep),
        max_features_keep=(
            None if args.max_features_keep is None else int(args.max_features_keep)
        ),
        refresh_stride_steps=int(args.refresh_stride_steps),
    )
    result = build_stage1_v2_feature_policy(
        run_id_or_path=str(run_id_or_path),
        project_root=PROJECT_ROOT,
        output_dir=args.output_dir,
        policy_version=args.policy_version,
        config=cfg,
    )
    print(json.dumps(result["summary"], indent=2))
    print(f"\nRegistry: {result['registry_path']}")
    print(f"Build summary: {result['build_summary_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
