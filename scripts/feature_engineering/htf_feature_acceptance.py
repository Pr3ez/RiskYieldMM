from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from fnmatch import fnmatchcase
from hashlib import sha256
from typing import Iterable


@dataclass(frozen=True)
class FinalOutputFeatureRule:
    pattern: str
    applies_to: tuple[str, ...]
    category: str
    reason: str


# Explicit final-output feature acceptance policy for currently known
# structural design-mismatch families. These rules apply only to model-facing
# optimized/helper outputs. Raw feature-stage artifacts remain unchanged so we
# can keep tracing and redesigning the underlying formulas separately.
FINAL_OUTPUT_FEATURE_RULES: tuple[FinalOutputFeatureRule, ...] = (
    FinalOutputFeatureRule(
        pattern="F_I_N_S_fundingZscore_*_zsc",
        applies_to=("optimized", "helpers"),
        category="needs_redesign",
        reason=(
            "rolling z-score on broadcast 8h stepwise funding creates structurally "
            "null-heavy outputs in final saved rows"
        ),
    ),
    FinalOutputFeatureRule(
        pattern="D_dist_avg_high_w240",
        applies_to=("optimized", "helpers"),
        category="temporarily_excluded",
        reason=(
            "batch-local warmup window is structurally incompatible with final "
            "front-half 1m saved rows"
        ),
    ),
    FinalOutputFeatureRule(
        pattern="D_dist_avg_low_w240",
        applies_to=("optimized", "helpers"),
        category="temporarily_excluded",
        reason=(
            "batch-local warmup window is structurally incompatible with final "
            "front-half 1m saved rows"
        ),
    ),
    FinalOutputFeatureRule(
        pattern="D_dist_top5_high_w240",
        applies_to=("optimized", "helpers"),
        category="temporarily_excluded",
        reason=(
            "batch-local warmup window is structurally incompatible with final "
            "front-half 1m saved rows"
        ),
    ),
    FinalOutputFeatureRule(
        pattern="H_*_egarch_asymmetry",
        applies_to=("helpers",),
        category="needs_redesign",
        reason=(
            "Nelson 1991 leverage parameter trace is emitted as a fitted constant "
            "array in the current helper contract; source-backed audit on 2026-04-12 "
            "found it globally degenerate for model-facing HTF helper outputs"
        ),
    ),
    FinalOutputFeatureRule(
        pattern="H_*_egarch_persistence",
        applies_to=("helpers",),
        category="needs_redesign",
        reason=(
            "Nelson 1991 persistence parameter trace is emitted as a fitted constant "
            "array in the current helper contract; source-backed audit on 2026-04-12 "
            "found it globally degenerate for model-facing HTF helper outputs"
        ),
    ),
)

FINAL_OUTPUT_LABEL_ONLY_COLUMNS: frozenset[str] = frozenset(
    {
        "target_long",
        "target_short",
        "target_4class",
        "target_breakfree",
        "target_name",
        "close_end",
        "end_return",
        "remaining_bars",
        "dist_avg_high",
        "dist_avg_low",
        "dist_top5_high",
        "dist_bot5_low",
        "bar_pos_15m",
    }
)


_policy_payload = {
    "rules": [asdict(rule) for rule in FINAL_OUTPUT_FEATURE_RULES],
}
FINAL_OUTPUT_FEATURE_POLICY_SIGNATURE = sha256(
    json.dumps(_policy_payload, sort_keys=True).encode("utf-8")
).hexdigest()
FINAL_OUTPUT_FEATURE_POLICY_VERSION = f"2026-03-30-{FINAL_OUTPUT_FEATURE_POLICY_SIGNATURE[:12]}"


def get_final_output_excluded_columns(
    columns: Iterable[str],
    *,
    stage: str,
) -> list[str]:
    """Return explicitly excluded model-facing columns for a given output stage."""
    excluded: list[str] = []
    for col in columns:
        if any(
            stage in rule.applies_to and fnmatchcase(col, rule.pattern)
            for rule in FINAL_OUTPUT_FEATURE_RULES
        ):
            excluded.append(col)
    return sorted(set(excluded))


def get_final_output_forbidden_columns(
    columns: Iterable[str],
    *,
    stage: str,
) -> list[str]:
    """Return columns that must not appear in optimized/helper model outputs."""
    stage_excluded = set(get_final_output_excluded_columns(columns, stage=stage))
    label_only = set(columns) & FINAL_OUTPUT_LABEL_ONLY_COLUMNS
    return sorted(stage_excluded | label_only)


def describe_final_output_exclusions(
    columns: Iterable[str],
    *,
    stage: str,
) -> list[dict[str, str]]:
    """Return matching exclusion rules for the provided columns."""
    seen: set[tuple[str, str]] = set()
    matched: list[dict[str, str]] = []
    for col in columns:
        for rule in FINAL_OUTPUT_FEATURE_RULES:
            if stage not in rule.applies_to or not fnmatchcase(col, rule.pattern):
                continue
            key = (col, rule.pattern)
            if key in seen:
                continue
            seen.add(key)
            matched.append(
                {
                    "column": col,
                    "pattern": rule.pattern,
                    "category": rule.category,
                    "reason": rule.reason,
                }
            )
    return matched
