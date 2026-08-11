from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest

from regression_feature_engineering.materialize_features import materialize_regression_feature_roots
from regression_feature_engineering.validate_features import _diagnostic_feature_columns, _family_slug, validate_regression_feature_roots


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_feature_validator_writes_report_and_index(tmp_path: Path) -> None:
    label_dir = tmp_path / "data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m"
    canonical_dir = tmp_path / "data/htf_multiasset/btcusdt/htf_canonical_ohlcv/15m"
    label_dir.mkdir(parents=True)
    canonical_dir.mkdir(parents=True)

    labels = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:15:00"), _ts("2026-01-01T00:16:00"), _ts("2026-01-01T00:17:00")],
            "batch_id": [1, 1, 1],
            "close": [101.0, 102.0, 103.0],
            "tb_volatility_pct": [0.01, 0.011, 0.012],
            "tb_atr_pct_14": [0.012, 0.012, 0.012],
            "tb_realized_vol_120": [0.006, 0.006, 0.006],
            "target_reg_distance_valid_v2": [True, True, True],
            "target_reg_distance_horizon_vol_pct_v2": [0.1, 0.1, 0.1],
            "target_reg_distance_future_bars_v2": [16, 16, 16],
            "target_reg_distance_up_extreme_pct_v2": [0.01, 0.02, 0.03],
            "target_reg_distance_down_extreme_pct_v2": [0.03, 0.02, 0.01],
            "target_reg_distance_up_extreme_hvol_v2": [0.1, 0.2, 0.3],
            "target_reg_distance_up_mean_high_hvol_v2": [0.05, 0.1, 0.15],
            "target_reg_distance_down_mean_low_hvol_v2": [0.15, 0.1, 0.05],
            "target_reg_distance_down_extreme_hvol_v2": [0.3, 0.2, 0.1],
        }
    )
    labels.write_parquet(label_dir / "batch_0001.parquet")

    bars = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:00:00")],
            "open": [100.0],
            "high": [103.0],
            "low": [99.0],
            "close": [102.0],
            "volume": [10.0],
        }
    )
    bars.write_parquet(canonical_dir / "btcusdt_15m_canonical.parquet")

    materialize_regression_feature_roots(
        project_root=tmp_path,
        assets=("BTCUSDT",),
        roots=("8h/B",),
        families=("foundation_alignment", "volatility_state"),
        timeframes=("15m",),
        lookbacks=(2,),
    )

    summaries = validate_regression_feature_roots(
        project_root=tmp_path,
        assets=("BTCUSDT",),
        roots=("8h/B",),
        timeframes=("15m",),
        output_dir=tmp_path / "reports",
    )

    assert len(summaries) == 1
    assert summaries[0].joined_rows == 3
    assert summaries[0].valid_rows == 3
    assert summaries[0].duplicate_count == 0
    assert summaries[0].future_close_violations == 0
    assert summaries[0].report_path.exists()
    assert (tmp_path / "reports/validation_index.csv").exists()


def test_validator_rejects_wide_diagnostic_selection_without_override() -> None:
    feature_cols = tuple(f"rpf_accept_15m_signal_{idx}" for idx in range(4))

    with pytest.raises(ValueError, match="Selected 4 diagnostic feature columns"):
        _diagnostic_feature_columns(
            feature_cols,
            "rpf_accept_15m_",
            max_diagnostic_columns=3,
            allow_wide_diagnostics=False,
        )

    assert (
        _diagnostic_feature_columns(
            feature_cols,
            "rpf_accept_15m_",
            max_diagnostic_columns=3,
            allow_wide_diagnostics=True,
        )
        == feature_cols
    )


def test_validator_family_slug_is_bounded_for_large_family_sets() -> None:
    families = (
        "foundation_alignment",
        "volatility_state",
        "structural_room",
        "acceptance_persistence",
        "temporal_memory_transforms",
        "rejection_chop",
        "spike_breakout",
        "liquidity_volume_pressure",
        "regime_calendar_state",
        "interaction_confluence",
        "cross_asset_context",
        "unsupervised_factor_layer",
        "sequence_embedding_layer",
    )

    slug = _family_slug(families)

    assert len(slug) <= 96
    assert slug.startswith("families12_")
    assert _family_slug(("foundation_alignment",)) == "foundation_alignment"
