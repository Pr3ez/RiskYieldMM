#!/usr/bin/env python3
"""Build a deterministic point-in-time availability inventory for model features.

The inventory distinguishes a declared or code-guarded causal rule from a full
point-in-time certification.  Current historical canonical data do not retain
their original first-seen/revision clocks, and the RPF path has no production
inference implementation, so the script must not label those features fully
certified merely because their materialization catalog declares a causal rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "docs"
    / "validation"
    / "trading_prediction_feature_availability_audit_2026-07-14.json"
)
ANALYST_ARTIFACT = (
    PROJECT_ROOT
    / "models"
    / "analyst_cusum_meta"
    / "cusum-meta-logistic-all56-20260710-v2.artifact.json"
)
RPF_MANIFEST_GLOB = (
    "data/htf_multiasset/*/regression_path_features_v1/*/1m/manifest.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


ANALYST_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "log_return_directional": ("online.log_return", "decision.side"),
    "trend_score_directional": ("online.trend_score", "decision.side"),
    "trend_agreement_directional": ("online.trend_agreement", "decision.side"),
    "trend_state_alignment": ("online.trend_state_code", "decision.side"),
    "path_quality": ("online.path_quality",),
    "risk_unit_fraction": ("decision.risk_unit", "decision.entry_reference"),
    "stop_risk_units": ("policy.stop_risk_units",),
    "target_risk_units": ("policy.target_risk_units",),
    "timeout_horizon_minutes_log1p": (
        "policy.timeout_target_bars",
        "policy.target_interval_seconds",
    ),
    "estimated_roundtrip_cost_bps": ("policy.estimated_roundtrip_cost_bps",),
    "trend_z_fast_directional": ("online.trend_z_fast", "decision.side"),
    "trend_z_medium_directional": ("online.trend_z_medium", "decision.side"),
    "trend_z_slow_directional": ("online.trend_z_slow", "decision.side"),
    "path_efficiency_fast": ("online.path_efficiency_fast",),
    "path_efficiency_medium": ("online.path_efficiency_medium",),
    "path_efficiency_slow": ("online.path_efficiency_slow",),
    "trend_component_fast_directional": (
        "online.trend_component_fast",
        "decision.side",
    ),
    "trend_component_medium_directional": (
        "online.trend_component_medium",
        "decision.side",
    ),
    "trend_component_slow_directional": (
        "online.trend_component_slow",
        "decision.side",
    ),
    "ewma_vol_fast_pct": ("online.ewma_vol_fast_pct",),
    "ewma_vol_medium_pct": ("online.ewma_vol_medium_pct",),
    "ewma_vol_slow_pct": ("online.ewma_vol_slow_pct",),
    "fast_slow_ratio": ("online.fast_slow_ratio",),
    "volatility_pressure": ("online.volatility_pressure",),
    "range_pressure": ("online.range_pressure",),
    "cusum_regime_alignment": ("cusum.regime", "decision.side"),
    "cusum_standardized_residual_directional": (
        "cusum.residual",
        "cusum.res_std",
        "decision.side",
    ),
    "cusum_pressure_balance_directional": (
        "cusum.bull_pressure",
        "cusum.bear_pressure",
        "decision.side",
    ),
    "cusum_pressure_fraction": ("cusum.pressure_pct",),
    "cusum_same_side_start": ("cusum.bull_start_or_bear_start_for_decision_side",),
    "cusum_opposite_side_start": ("cusum.bear_start_or_bull_start_for_decision_side",),
    "cusum_scale_ready": ("cusum.scale_ready",),
}

ANALYST_CONSTANT_FEATURES = {
    "stop_risk_units",
    "target_risk_units",
    "estimated_roundtrip_cost_bps",
    "cusum_regime_alignment",
    "cusum_pressure_balance_directional",
    "cusum_pressure_fraction",
    "cusum_same_side_start",
    "cusum_opposite_side_start",
    "cusum_scale_ready",
}


def _analyst_entries() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    artifact = _load_json(ANALYST_ARTIFACT)
    names = tuple(str(value) for value in artifact["feature_names"])
    if set(names) != set(ANALYST_DEPENDENCIES):
        missing = sorted(set(names) - set(ANALYST_DEPENDENCIES))
        extra = sorted(set(ANALYST_DEPENDENCIES) - set(names))
        raise ValueError(
            f"Analyst dependency map mismatch: missing={missing}, extra={extra}"
        )

    entries: list[dict[str, Any]] = []
    for name in names:
        dependencies = ANALYST_DEPENDENCIES[name]
        source_group = (
            "online_indicator_snapshot"
            if any(value.startswith("online.") for value in dependencies)
            else "cusum_snapshot"
            if any(value.startswith("cusum.") for value in dependencies)
            else "decision_and_locked_policy"
        )
        entries.append(
            {
                "system": "analyst_cusum_meta",
                "name": name,
                "family": source_group,
                "raw_dependencies": list(dependencies),
                "source_timeframes": ["selected_timeframe_and_causal_online_state"],
                "declared_availability": "validated_snapshot_at_or_before_decision",
                "information_cutoff_rule": (
                    "online.source_timestamp, online.available_at, "
                    "cusum.source_timestamp, and cusum.available_at used by this feature "
                    "must be <= decision_at; locked policy values must be effective before decision_at"
                ),
                "current_row_policy": (
                    "A completed current bar may contribute only through an online/CUSUM snapshot "
                    "whose stated available_at is <= decision_at"
                ),
                "fit_scope": (
                    "Feature calculation is deterministic from causal online state; model median "
                    "imputation and scaling are fitted inside each training fold"
                ),
                "historical_point_in_time_status": (
                    "UNVERIFIED_CURRENT_REVISION_SOURCE_HAS_NO_FIRST_SEEN_CLOCK"
                ),
                "live_reproducibility_status": (
                    "IMPLEMENTED_INPUT_CLOCK_GUARDS_REQUIRES_VERSION_MATCHED_PARITY_TEST"
                ),
                "leakage_audit_status": (
                    "CODE_GUARDED_BUT_NOT_HISTORICAL_VINTAGE_CERTIFIED"
                ),
                "constant_in_v2_training_artifact": name in ANALYST_CONSTANT_FEATURES,
                "evidence": [
                    "Risk_Yield_Meta_Model_Analyst_0_0_1/trade_ml/features.py",
                    str(ANALYST_ARTIFACT.relative_to(PROJECT_ROOT)),
                ],
            }
        )
    return entries, {
        "artifact_path": str(ANALYST_ARTIFACT.relative_to(PROJECT_ROOT)),
        "artifact_sha256": _sha256(ANALYST_ARTIFACT),
        "feature_count": len(entries),
        "constant_feature_count": sum(
            bool(value["constant_in_v2_training_artifact"]) for value in entries
        ),
        "inventory_complete": True,
        "strict_point_in_time_certification_complete": False,
    }


RPF_CUTOFF_RULES = {
    "prediction_time": (
        "All source values must be observable after the completed base row and no later than "
        "decision_ts; the current materialization lacks an explicit decision_ts column"
    ),
    "prediction_time_with_prior_rolling_window": (
        "The completed base row and every prior rolling observation must be available no later "
        "than decision_ts"
    ),
    "closed_bar_asof_only": (
        "Every source bar must have bar_close_ts <= decision_ts and be selected by backward as-of join"
    ),
    "previous_closed_channel_asof_only": (
        "Channel/level inputs must come from bars closed strictly before the represented current bar "
        "and be available by decision_ts"
    ),
    "previous_closed_levels_or_closed_bar_asof_only": (
        "Break levels must be from previous closed bars; other inputs require bar_close_ts <= decision_ts"
    ),
    "prior_rows_only_streaming_state": (
        "State emitted for the current row may use only source rows processed before that row; any "
        "outcome-derived state additionally requires source label_known_ts <= decision_ts"
    ),
    "known_at_prediction_time": (
        "Calendar/session metadata must be authoritative and effective at decision_ts; inferred "
        "observed-session calendars cannot certify this rule"
    ),
    "latest_closed_bar_metadata_asof_only": (
        "Metadata must describe the latest source bar whose close and availability are <= decision_ts"
    ),
    "derived_from_causal_component_features": (
        "The maximum availability timestamp of every component feature must be <= decision_ts"
    ),
    "exact_timestamp_pair_bar_then_closed_bar_asof": (
        "Both target and peer observations must be available in the same decision snapshot; every "
        "higher-timeframe dependency must be closed by decision_ts and future universe membership is forbidden"
    ),
    "derived_from_causal_component_features_no_global_fit": (
        "Every component feature must be available by decision_ts and the deterministic factor proxy "
        "must not use a full-sample fit"
    ),
    "derived_from_causal_factor_proxies_no_encoder_fit": (
        "Every factor-proxy input must be available by decision_ts and the deterministic sequence "
        "summary must not use a future/full-sample encoder fit"
    ),
}


def _rpf_current_row_policy(availability: str) -> str:
    if availability == "prior_rows_only_streaming_state":
        return "PRIOR_ROWS_ONLY"
    if availability.startswith("previous_closed"):
        return "PREVIOUS_CLOSED_LEVELS; OTHER COMPLETED CURRENT INPUTS CONDITIONAL"
    if availability == "known_at_prediction_time":
        return "NO PRICE ROW REQUIRED; METADATA MUST BE EFFECTIVE AT DECISION"
    return "COMPLETED CURRENT INPUT MAY BE USED ONLY AFTER EXPLICIT BAR_CLOSE/AVAILABLE/DECISION CLOCK"


def _rpf_fit_scope(family: str, availability: str) -> str:
    if family == "temporal_memory_transforms":
        return "prior-only streaming state; model transforms remain fold-local"
    if availability.endswith("no_global_fit"):
        return "current implementation declares deterministic no-global-fit proxies"
    if availability.endswith("no_encoder_fit"):
        return "current implementation declares deterministic summaries with no encoder fit"
    return "deterministic feature calculation; all model preprocessing/selection must remain fold-local"


def _rpf_entries() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest_paths = sorted(PROJECT_ROOT.glob(RPF_MANIFEST_GLOB))
    if not manifest_paths:
        raise FileNotFoundError(f"No RPF manifests matched {RPF_MANIFEST_GLOB}")

    scopes_by_feature: dict[str, list[str]] = defaultdict(list)
    metadata_by_feature: dict[str, dict[str, Any]] = {}
    normalizations_by_feature: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    scope_rows: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for manifest_path in manifest_paths:
        manifest = _load_json(manifest_path)
        catalog_path = manifest_path.with_name("feature_catalog.json")
        catalog = _load_json(catalog_path)
        manifest_names = tuple(str(value) for value in manifest["feature_columns"])
        catalog_names = tuple(str(value["name"]) for value in catalog)
        if manifest_names != catalog_names:
            raise ValueError(f"Manifest/catalog order mismatch: {manifest_path}")
        scope = f"{manifest['asset']}/{manifest['root_id']}"
        scope_rows.append(
            {
                "scope": scope,
                "manifest_path": str(manifest_path.relative_to(PROJECT_ROOT)),
                "manifest_sha256": _sha256(manifest_path),
                "catalog_path": str(catalog_path.relative_to(PROJECT_ROOT)),
                "catalog_sha256": _sha256(catalog_path),
                "feature_count": int(manifest["feature_count"]),
                "schema_hash": str(manifest["schema_hash"]),
                "row_count": int(manifest["row_count"]),
            }
        )
        for item in catalog:
            name = str(item["name"])
            normalized = {
                "family": str(item["family"]),
                "source_columns": [str(value) for value in item["source_columns"]],
                "source_timeframes": [
                    str(value) for value in item["source_timeframes"]
                ],
                "declared_availability": str(item["availability"]),
                "normalization": str(item["normalization"]),
                "target_intent": [str(value) for value in item["target_intent"]],
            }
            prior = metadata_by_feature.get(name)
            if prior is not None and prior != normalized:
                conflicts.append(
                    {
                        "name": name,
                        "scope": scope,
                        "prior": prior,
                        "current": normalized,
                    }
                )
            else:
                metadata_by_feature[name] = normalized
            normalizations_by_feature[name][normalized["normalization"]].append(scope)
            scopes_by_feature[name].append(scope)

    non_normalization_conflicts = []
    for conflict in conflicts:
        prior = dict(conflict["prior"])
        current = dict(conflict["current"])
        prior.pop("normalization", None)
        current.pop("normalization", None)
        if prior != current:
            non_normalization_conflicts.append(conflict)
    if non_normalization_conflicts:
        raise ValueError(
            "RPF feature catalog has causal-metadata conflicts beyond normalization: "
            f"{non_normalization_conflicts[:3]}"
        )

    entries: list[dict[str, Any]] = []
    for name in sorted(metadata_by_feature):
        metadata = metadata_by_feature[name]
        availability = metadata["declared_availability"]
        if availability not in RPF_CUTOFF_RULES:
            raise ValueError(
                f"Missing cutoff rule for RPF availability={availability!r}"
            )
        entries.append(
            {
                "system": "rpf_research",
                "name": name,
                **metadata,
                "normalization_variants": {
                    normalization: sorted(scopes)
                    for normalization, scopes in sorted(
                        normalizations_by_feature[name].items()
                    )
                },
                "scopes": sorted(scopes_by_feature[name]),
                "information_cutoff_rule": RPF_CUTOFF_RULES[availability],
                "current_row_policy": _rpf_current_row_policy(availability),
                "fit_scope": _rpf_fit_scope(metadata["family"], availability),
                "historical_point_in_time_status": (
                    "UNVERIFIED_CURRENT_REVISION_SOURCE_AND_EXPLICIT_DECISION_TS_ABSENT"
                ),
                "live_reproducibility_status": (
                    "NOT_IMPLEMENTED_IN_CURRENT_ANALYST_LIVE_INFERENCE_PATH"
                ),
                "leakage_audit_status": (
                    "CATALOG_DECLARED_CAUSAL_BUT_NOT_PER_FEATURE_POINT_IN_TIME_CERTIFIED"
                ),
                "evidence": sorted(
                    {
                        str(
                            (
                                PROJECT_ROOT
                                / "data"
                                / "htf_multiasset"
                                / scope.split("/", 1)[0].lower()
                                / "regression_path_features_v1"
                                / scope.split("/", 1)[1]
                                / "1m"
                                / "feature_catalog.json"
                            ).relative_to(PROJECT_ROOT)
                        )
                        for scope in scopes_by_feature[name]
                    }
                ),
            }
        )

    family_counts = Counter(value["family"] for value in entries)
    availability_counts = Counter(value["declared_availability"] for value in entries)
    return entries, {
        "manifest_count": len(scope_rows),
        "scope_manifests": scope_rows,
        "unique_feature_count": len(entries),
        "family_counts": dict(sorted(family_counts.items())),
        "availability_counts": dict(sorted(availability_counts.items())),
        "catalog_metadata_conflict_count": len(conflicts),
        "catalog_features_with_normalization_variants": len(
            {value["name"] for value in conflicts}
        ),
        "catalog_non_normalization_conflict_count": len(non_normalization_conflicts),
        "inventory_complete_for_all_current_rpf_manifests": True,
        "strict_point_in_time_certification_complete": False,
        "blocking_reasons": [
            "RPF row key is a bar-open timestamp and explicit feature_available_ts/decision_ts is absent",
            "historical canonical inputs do not preserve first-seen/revision clocks",
            "RPF features are not implemented in the current live Analyst inference path",
            "cross-asset peer age/universe membership and authoritative session calendar are incomplete",
        ],
    }


def build_payload() -> dict[str, Any]:
    analyst_entries, analyst_summary = _analyst_entries()
    rpf_entries, rpf_summary = _rpf_entries()
    entries = [*analyst_entries, *rpf_entries]
    required = {
        "system",
        "name",
        "family",
        "information_cutoff_rule",
        "current_row_policy",
        "fit_scope",
        "historical_point_in_time_status",
        "live_reproducibility_status",
        "leakage_audit_status",
        "evidence",
    }
    missing = [
        {
            "system": value.get("system"),
            "name": value.get("name"),
            "missing": sorted(required - value.keys()),
        }
        for value in entries
        if required - value.keys()
    ]
    if missing:
        raise ValueError(f"Feature audit entries are incomplete: {missing[:3]}")
    return {
        "schema_version": "trading_prediction_feature_availability_audit_v1",
        "audit_date": "2026-07-14",
        "strict_rule": (
            "A feature is point-in-time certified only when every raw dependency's actual "
            "first-seen availability is <= decision_ts and replay/live parity has passed"
        ),
        "summary": {
            "total_unique_model_features": len(entries),
            "analyst_feature_count": len(analyst_entries),
            "rpf_unique_feature_count": len(rpf_entries),
            "entries_missing_required_audit_fields": len(missing),
            "inventory_complete": True,
            "strict_point_in_time_certification_complete": False,
            "deployment_blocked_by_feature_certification": True,
        },
        "analyst": analyst_summary,
        "rpf": rpf_summary,
        "features": entries,
    }


def _serialized_payload() -> str:
    return json.dumps(build_payload(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the existing output differs from a fresh deterministic build.",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    content = _serialized_payload()
    if args.check:
        if not output.exists():
            raise FileNotFoundError(output)
        if output.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Feature availability audit is stale: {output}")
        print(f"feature availability audit current: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
