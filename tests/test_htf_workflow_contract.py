"""Contract tests for the current HTF workflow.

These tests intentionally inspect declarative source contracts without importing
the heavy HTF modules. The active workflow depends on Polars, CatBoost, GPU
runtime, and local artifacts; these tests should still catch stale config drift
in a lightweight unit-test pass.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _module_tree(relative_path: str) -> ast.Module:
    return ast.parse((PROJECT_ROOT / relative_path).read_text())


def _top_level_assignments(tree: ast.Module) -> dict[str, ast.AST]:
    assignments: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = node.value
    return assignments


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    return ast.literal_eval(_top_level_assignments(tree)[name])


def _string_path_parts(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return [*_string_path_parts(node.left), *_string_path_parts(node.right)]
    if isinstance(node, ast.Name):
        return []
    return []


def _extract_roots(tree: ast.Module) -> dict[str, dict[str, Any]]:
    roots_node = _top_level_assignments(tree)["ROOTS"]
    assert isinstance(roots_node, ast.Dict)

    roots: dict[str, dict[str, Any]] = {}
    for key_node, value_node in zip(roots_node.keys, roots_node.values, strict=True):
        assert isinstance(key_node, ast.Constant)
        assert isinstance(value_node, ast.Dict)
        root_cfg: dict[str, Any] = {}
        for cfg_key_node, cfg_value_node in zip(
            value_node.keys,
            value_node.values,
            strict=True,
        ):
            assert isinstance(cfg_key_node, ast.Constant)
            cfg_key = str(cfg_key_node.value)
            if cfg_key in {"features_dir", "labels_dir"}:
                root_cfg[cfg_key] = "/".join(_string_path_parts(cfg_value_node))
            else:
                root_cfg[cfg_key] = ast.literal_eval(cfg_value_node)
        roots[str(key_node.value)] = root_cfg
    return roots


def _extract_regime_configs(tree: ast.Module) -> dict[str, dict[str, Any]]:
    regime_node = _top_level_assignments(tree)["REGIME_CONFIGS"]
    assert isinstance(regime_node, ast.Dict)

    regimes: dict[str, dict[str, Any]] = {}
    for key_node, value_node in zip(regime_node.keys, regime_node.values, strict=True):
        assert isinstance(key_node, ast.Constant)
        assert isinstance(value_node, ast.Call)
        regimes[str(key_node.value)] = {
            keyword.arg: ast.literal_eval(keyword.value)
            for keyword in value_node.keywords
            if keyword.arg in {"name", "duration_hours", "shift_hours", "entry_window_hours"}
        }
    return regimes


def _string_constants_in_function(tree: ast.Module, function_name: str) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return {
                constant.value
                for constant in ast.walk(node)
                if isinstance(constant, ast.Constant) and isinstance(constant.value, str)
            }
    raise AssertionError(f"Function not found: {function_name}")


def test_htf_regime_config_matches_current_multiregime_contract() -> None:
    tree = _module_tree("scripts/feature_engineering/htf_multiregime_pipeline.py")

    assert _extract_regime_configs(tree) == {
        "8h": {
            "name": "8h",
            "duration_hours": 8,
            "shift_hours": 4,
            "entry_window_hours": 4,
        },
        "24h": {
            "name": "24h",
            "duration_hours": 24,
            "shift_hours": 12,
            "entry_window_hours": 12,
        },
        "7d": {
            "name": "7d",
            "duration_hours": 168,
            "shift_hours": 84,
            "entry_window_hours": 84,
        },
    }

    assert _literal_assignment(tree, "TARGET_TIMEFRAMES") == ("1m",)
    assert _literal_assignment(tree, "DISTANCE_TIMEFRAMES") == ("15m",)
    assert _literal_assignment(tree, "UPSTREAM_TIMEFRAMES") == ("1m", "15m")


def test_htf_family_metadata_preserves_legacy_alias_and_current_regime_fields() -> None:
    tree = _module_tree("scripts/feature_engineering/htf_multiregime_pipeline.py")

    family_meta_cols = _literal_assignment(tree, "FAMILY_META_COLS")
    assert family_meta_cols[0] == "period_8h_start"
    assert "batch_regime" in family_meta_cols
    assert "batch_duration_hours" in family_meta_cols
    assert "family_shift_hours" in family_meta_cols
    assert "entry_window_hours" in family_meta_cols


def test_stage1_latest_runner_targets_six_htf_roots() -> None:
    tree = _module_tree("scripts/analysis/htf_stage1_regime_family_walkforward.py")

    assert _literal_assignment(tree, "MODEL_NAME") == "catboost"
    assert _literal_assignment(tree, "TF") == "1m"
    assert _literal_assignment(tree, "TARGET_COL") == "target_4class"
    assert _literal_assignment(tree, "CLASS_NAMES_4") == [
        "DOWN_BALANCED",
        "DOWN_EXPANSION",
        "UP_BALANCED",
        "UP_EXPANSION",
    ]
    assert _literal_assignment(tree, "STAGE1_FALLBACK_MANUAL_TRIPLETS") == {
        "1m/target_4class": [(7, 1, 4), (2, 1, 3), (2, 2, 8), (2, 3, 9)]
    }

    roots = _extract_roots(tree)
    assert set(roots) == {"8h/B", "8h/C", "24h/B", "24h/C", "7d/B", "7d/C"}
    assert roots == {
        "8h/B": {
            "regime": "8h",
            "family": "B",
            "features_dir": "data/htf_with_helpers",
            "labels_dir": "data/htf_4class_labels",
            "run_id": "stage1_catboost_8h_b_live",
        },
        "8h/C": {
            "regime": "8h",
            "family": "C",
            "features_dir": "data/htf_with_helpers_shift4h",
            "labels_dir": "data/htf_4class_labels_shift4h",
            "run_id": "stage1_catboost_8h_c_live",
        },
        "24h/B": {
            "regime": "24h",
            "family": "B",
            "features_dir": "data/htf_with_helpers_24h",
            "labels_dir": "data/htf_4class_labels_24h",
            "run_id": "stage1_catboost_24h_b_live",
        },
        "24h/C": {
            "regime": "24h",
            "family": "C",
            "features_dir": "data/htf_with_helpers_24h_shift12h",
            "labels_dir": "data/htf_4class_labels_24h_shift12h",
            "run_id": "stage1_catboost_24h_c_live",
        },
        "7d/B": {
            "regime": "7d",
            "family": "B",
            "features_dir": "data/htf_with_helpers_7d",
            "labels_dir": "data/htf_4class_labels_7d",
            "run_id": "stage1_catboost_7d_b_live",
        },
        "7d/C": {
            "regime": "7d",
            "family": "C",
            "features_dir": "data/htf_with_helpers_7d_shift84h",
            "labels_dir": "data/htf_4class_labels_7d_shift84h",
            "run_id": "stage1_catboost_7d_c_live",
        },
    }


def test_stage1_runner_exposes_multiasset_dataset_assembly_flags() -> None:
    source = (
        PROJECT_ROOT / "scripts/analysis/htf_stage1_regime_family_walkforward.py"
    ).read_text()

    assert "--build-merged-dataset" in source
    assert "--target-assets" in source
    assert "--context-assets" in source
    assert "--multiasset-dataset-dir" in source
    assert "build_multiasset_stage1_dataset" in source


def test_stage1_feature_policy_excludes_multiasset_calendar_metadata() -> None:
    tree = _module_tree("scripts/htf_backtest/catboost/utils.py")
    excluded = _literal_assignment(tree, "MODEL_METADATA_EXCLUDE")

    assert {
        "asset_id",
        "calendar_id",
        "is_market_open",
        "is_synthetic_no_trade",
        "is_open_session_gap_fill",
        "minutes_since_prev_real_bar",
        "session_id",
        "session_date",
        "session_bar_pos",
        "session_minutes_to_close",
        "expected_rows_in_batch",
        "actual_rows_in_batch",
        "expected_entry_rows",
        "actual_entry_rows",
        "has_synthetic_open_gap_fill",
    } <= excluded
    assert "bar_in_batch_norm" not in excluded


def test_stage1_v1_artifact_contract_includes_required_audit_payloads() -> None:
    tree = _module_tree("scripts/htf_backtest/catboost/stage1_runner.py")
    constants = _string_constants_in_function(tree, "_stage1_required_artifact_paths")

    assert {
        "batch_metadata.json",
        "stage1",
        "stage1_step_summary.json",
        "stage1_config_snapshot.json",
        "stage1_combo_index.parquet",
        "stage1_fold_windows.parquet",
        "stage1_val_predictions.parquet",
        "stage1_pred_batch_predictions.parquet",
        "stage1_predecision_context.json",
        "stage1_predecision_context.parquet",
        "stage1_runtime_profile.json",
    } <= constants


def test_stage1_v2_artifact_contract_matches_current_selector_modes() -> None:
    from scripts.htf_backtest.catboost import stage1_v2_contract as contract

    assert contract.STAGE1_VERSION_V1 == "v1"
    assert contract.STAGE1_VERSION_V2 == "v2"
    assert contract.STAGE1_V2_EXECUTION_MODE_PARITY == "parity"
    assert contract.STAGE1_V2_EXECUTION_MODE_NESTED == "nested_selector"
    assert contract.STAGE1_V2_EXECUTION_MODE_FIXED_POLICY == "fixed_policy"

    payload = contract.stage1_v2_contract_payload(
        {"execution_mode": "nested_selector"}
    )
    assert payload["artifact_contract_version"] == "2026-04-20-stage1-v2-contract-v1"
    assert payload["execution_mode"] == "nested_selector"
    assert payload["root_artifacts"] == {
        "run_summary": "stage1_v2_run_summary.json",
        "progress": "stage1_v2_progress.parquet",
        "feature_importance_global": "stage1_v2_feature_importance_global.parquet",
        "feature_mask_global": "stage1_v2_feature_mask_global.parquet",
        "feature_stability": "stage1_v2_feature_stability.parquet",
        "baseline_vs_selected_root": "stage1_v2_baseline_vs_selected_root.parquet",
        "winner_change_summary": "stage1_v2_winner_change_summary.parquet",
    }
    assert payload["step_artifacts"] == {
        "summary": "stage1_v2_step_summary.json",
        "combo_metrics": "stage1_v2_combo_metrics.parquet",
        "feature_importance_steps": "stage1_v2_feature_importance_steps.parquet",
        "selected_features": "stage1_v2_selected_features.json",
        "selector_fold_outputs": "stage1_v2_selector_fold_outputs.parquet",
        "predictions_baseline": "stage1_v2_pred_batch_predictions_baseline.parquet",
        "predictions_selected": "stage1_v2_pred_batch_predictions_selected.parquet",
    }

    fixed_policy_payload = contract.stage1_v2_fixed_policy_contract_payload()
    assert fixed_policy_payload["artifact_contract_version"] == (
        "2026-04-20-stage1-v2-fixed-policy-v1"
    )
    assert fixed_policy_payload["root_artifacts"] == {
        "registry": "stage1_v2_fixed_policy_registry.json",
        "build_summary": "stage1_v2_fixed_policy_build_summary.json",
        "details_dir": "stage1_v2_fixed_policy_build",
        "per_combo_feature_stats": "stage1_v2_fixed_policy_build/per_combo_feature_stats.parquet",
        "combo_policy_summary": "stage1_v2_fixed_policy_build/combo_policy_summary.parquet",
        "final_mask_features": "stage1_v2_fixed_policy_build/final_mask_features.parquet",
    }
