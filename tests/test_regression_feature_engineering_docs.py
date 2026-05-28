from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "regression_feature_engineering"
DOCS = WORKSPACE / "docs"
CONFIG_PATH = WORKSPACE / "configs" / "regression_feature_engineering_v1.json"

FEATURE_SET = "regression_path_features_v1"
TARGET_VARIANT = "distance_horizon_vol_v2"
ROOT_IDS = ("8h_b", "8h_c", "24h_b", "24h_c", "7d_b", "7d_c")
TARGETS = (
    "target_reg_distance_up_extreme_hvol_v2",
    "target_reg_distance_up_mean_high_hvol_v2",
    "target_reg_distance_down_mean_low_hvol_v2",
    "target_reg_distance_down_extreme_hvol_v2",
)
OUTPUT_PATH = "data/htf_multiasset/{asset}/regression_path_features_v1/{root_id}/1m/"


def _doc_texts() -> dict[str, str]:
    paths = [
        WORKSPACE / "README.md",
        DOCS / "architecture.md",
        DOCS / "workflow.md",
        DOCS / "data_contract.md",
        DOCS / "feature_taxonomy.md",
        DOCS / "htf_feature_helper_inventory.md",
        DOCS / "research_feature_signal_backlog.md",
        DOCS / "feature_implementation_todo.md",
        DOCS / "regression_target_rollout.md",
        DOCS / "current_htf_feature_inventory.md",
        DOCS / "zero_target_validation.md",
        DOCS / "optimization_strategy.md",
        DOCS / "metadata_and_lineage.md",
        DOCS / "documentation_index.md",
    ]
    return {str(path.relative_to(WORKSPACE)): path.read_text() for path in paths}


def test_regression_feature_engineering_package_imports() -> None:
    import regression_feature_engineering

    assert regression_feature_engineering.__version__


def test_regression_feature_engineering_config_contract() -> None:
    cfg = json.loads(CONFIG_PATH.read_text())

    assert cfg["feature_set"] == FEATURE_SET
    assert cfg["target_variant"] == TARGET_VARIANT
    assert tuple(cfg["root_ids"]) == ROOT_IDS
    assert tuple(cfg["targets"]) == TARGETS
    assert cfg["output_path_template"] == OUTPUT_PATH


def test_regression_feature_family_registry_contract() -> None:
    from regression_feature_engineering.core.registry import (
        FEATURE_FAMILIES,
        feature_family_registry,
    )

    expected = (
        "foundation_alignment",
        "volatility_state",
        "structural_room",
        "acceptance_persistence",
        "rejection_chop",
        "spike_breakout",
        "liquidity_volume_pressure",
        "cross_asset_context",
        "unsupervised_factor_layer",
    )

    registry = feature_family_registry()
    assert FEATURE_FAMILIES == expected
    assert tuple(item.family_id for item in registry) == expected
    assert tuple(item.phase for item in registry) == tuple(range(1, 10))
    assert len({item.output_prefix for item in registry}) == len(registry)
    assert registry[0].status == "planned"
    assert registry[-1].status == "deferred"
    assert all(item.availability_rule for item in registry)
    assert all(item.target_intent for item in registry)


def test_regression_feature_engineering_docs_exist_and_have_standard_header() -> None:
    for rel_path, text in _doc_texts().items():
        assert text.strip(), rel_path
        for heading in (
            "## Purpose",
            "## Current Status",
            "## Scope",
            "## Source Of Truth",
            "## What This Does Not Decide",
        ):
            assert heading in text, f"{rel_path} missing {heading}"


def test_regression_feature_engineering_docs_use_canonical_terms() -> None:
    combined = "\n".join(_doc_texts().values())

    assert FEATURE_SET in combined
    assert TARGET_VARIANT in combined
    assert "BTCUSDT 8h/B" in combined
    for root_id in ROOT_IDS:
        assert root_id in combined
    for target in TARGETS:
        assert target in combined


def test_regression_feature_engineering_output_path_has_single_doc_contract() -> None:
    combined = "\n".join(_doc_texts().values())

    assert combined.count(OUTPUT_PATH) == 1
    assert OUTPUT_PATH in (DOCS / "data_contract.md").read_text()


def test_htf_feature_helper_inventory_documents_current_families() -> None:
    text = (DOCS / "htf_feature_helper_inventory.md").read_text()

    for feature_template in (
        "M_P_logReturn_pct",
        "V_atrPct_{short,med,long}_pct",
        "N_P_V_pctB_{short,med,long}_bnd",
        "L_M_S_obv_{long,xlong}_zsc",
        "C_N_upperShadow_bnd",
        "D_F_basis_pct",
        "X_D_oiRetPressure_{short,med,long}_pct",
    ):
        assert feature_template in text

    for helper in ("OU Helper", "GARCH Helper", "CUSUM Helper", "Kalman Helper", "EGARCH Helper"):
        assert helper in text

    for concept in (
        "volatility state",
        "structural room",
        "acceptance",
        "persistence",
        "spike capacity",
        "rejection",
        "chop",
        "cross-asset pressure",
    ):
        assert concept in text


def test_research_feature_signal_backlog_documents_later_candidates() -> None:
    text = (DOCS / "research_feature_signal_backlog.md").read_text()

    for signal_group in (
        "Multi-Timeframe Closed-Bar Context",
        "Volatility Denominator And Expansion State",
        "Structural Room And Price Location",
        "Acceptance And Persistence",
        "Spike, Breakout, And Breakdown Capacity",
        "Rejection, Chop, And Two-Sided Path Risk",
        "Cross-Asset Relative Context",
        "Session, Calendar, And Market-Open State",
        "Liquidity And Volume Pressure",
    ):
        assert signal_group in text

    for temporal_rule in (
        "closed bars available at the prediction timestamp",
        "backward-looking as-of semantics",
        "fit on historical training windows only",
    ):
        assert temporal_rule in text


def test_regression_target_rollout_documents_full_matrix() -> None:
    text = (DOCS / "regression_target_rollout.md").read_text()

    assert "8 assets x 6 roots x 4 regression target columns = 192 target series" in text
    for asset in ("BTCUSDT", "ETHUSDT", "EURUSD", "USDJPY", "GC", "CL", "ES", "NQ"):
        assert asset in text
    for root in ("8h/B", "8h/C", "24h/B", "24h/C", "7d/B", "7d/C"):
        assert root in text
    for command in (
        "materialize_stage1_regression_targets.py",
        "validate_stage1_regression_targets.py",
    ):
        assert command in text


def test_feature_implementation_todo_tracks_all_phases() -> None:
    text = (DOCS / "feature_implementation_todo.md").read_text()

    for family_id in (
        "foundation_alignment",
        "volatility_state",
        "structural_room",
        "acceptance_persistence",
        "rejection_chop",
        "spike_breakout",
        "liquidity_volume_pressure",
        "cross_asset_context",
        "unsupervised_factor_layer",
    ):
        assert family_id in text

    for required_field in (
        "source input paths and schema hash",
        "feature count and output prefix",
        "target relationship table for all four target columns",
        "walk-forward ablation result",
        "final status: `pending`, `accepted`, `quarantined`, or `rejected`",
    ):
        assert required_field in text
