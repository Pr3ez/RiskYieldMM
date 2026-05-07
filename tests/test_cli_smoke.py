from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("relative_path", "expected"),
    [
        ("update_data.py", "Core data update orchestrator"),
        ("fetchingByBit/update_data.py", "Bybit Data Pipeline"),
        ("fetchingMultiAsset/update_data.py", "Multi-Asset Data Pipeline"),
        ("fetchingMultiAsset/preflight_providers.py", "Safe readiness checks"),
        ("fetchingMultiAsset/fetch_databento.py", "Databento futures"),
        ("fetchingMultiAsset/fetch_yfinance.py", "Yahoo Finance recent-tail"),
        ("fetchingMultiAsset/aggregate_ohlcv.py", "Aggregate normalized"),
        (
            "scripts/analysis/htf_stage1_v2_pairwise_prediction_audit.py",
            "pairwise relationship",
        ),
        (
            "scripts/analysis/htf_stage1_v2_subset_reduction_audit.py",
            "fixed combo subsets",
        ),
        (
            "scripts/analysis/htf_stage1_v2_loss_discounted_selector_audit.py",
            "discounted past loss",
        ),
    ],
)
def test_dataset_free_cli_help_smoke(relative_path: str, expected: str) -> None:
    result = subprocess.run(
        [sys.executable, relative_path, "--help"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert expected in result.stdout
