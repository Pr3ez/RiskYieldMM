"""Materialize causal regression path features.

This entrypoint is intentionally separate from `notebooks/htf_pythonscript.py`.
It reads existing local artifacts and writes only
`regression_path_features_v1` outputs.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from regression_feature_engineering.core.alignment import (  # noqa: E402
    DEFAULT_TIMEFRAMES,
    OHLCV_COLUMNS,
    align_prefix,
    alignment_diagnostics,
    join_all_closed_bar_context,
    normalize_timeframes,
    source_prefix,
)
from regression_feature_engineering.core.config import load_config  # noqa: E402
from regression_feature_engineering.core.paths import (  # noqa: E402
    FEATURE_SET,
    TARGET_VARIANT,
    canonical_ohlcv_path,
    regression_feature_root,
    regression_label_root,
)
from regression_feature_engineering.core.registry import (  # noqa: E402
    FeatureDefinition,
    feature_family_registry,
)
from regression_feature_engineering.features.acceptance_persistence import (  # noqa: E402
    DEFAULT_ACCEPT_LOOKBACKS,
    add_acceptance_persistence_features,
    enrich_acceptance_persistence_sources,
    feature_columns as acceptance_feature_columns,
    source_columns as acceptance_source_columns,
)
from regression_feature_engineering.features.cross_asset_context import (  # noqa: E402
    DEFAULT_CROSS_ASSET_PEERS,
    DEFAULT_XASSET_LOOKBACKS,
    add_cross_asset_context_features,
    build_cross_asset_pair_sources,
    feature_columns as cross_asset_feature_columns,
    source_columns as cross_asset_source_columns,
)
from regression_feature_engineering.features.liquidity_volume_pressure import (  # noqa: E402
    DEFAULT_LIQ_LOOKBACKS,
    add_liquidity_volume_pressure_features,
    enrich_liquidity_volume_pressure_sources,
    feature_columns as liquidity_feature_columns,
    source_columns as liquidity_source_columns,
)
from regression_feature_engineering.features.interaction_confluence import (  # noqa: E402
    DEFAULT_CONFLUENCE_LOOKBACKS,
    add_interaction_confluence_features,
    feature_columns as interaction_confluence_feature_columns,
)
from regression_feature_engineering.features.rejection_chop import (  # noqa: E402
    DEFAULT_CHOP_LOOKBACKS,
    add_rejection_chop_features,
    enrich_rejection_chop_sources,
    feature_columns as rejection_chop_feature_columns,
    source_columns as rejection_chop_source_columns,
)
from regression_feature_engineering.features.regime_calendar_state import (  # noqa: E402
    DEFAULT_REGIME_LOOKBACKS,
    add_regime_calendar_state_features,
    enrich_regime_calendar_state_sources,
    feature_columns as regime_calendar_feature_columns,
    source_columns as regime_calendar_source_columns,
)
from regression_feature_engineering.features.sequence_embedding_layer import (  # noqa: E402
    DEFAULT_SEQUENCE_LOOKBACKS,
    add_sequence_embedding_layer_features,
    feature_columns as sequence_embedding_feature_columns,
)
from regression_feature_engineering.features.spike_breakout import (  # noqa: E402
    DEFAULT_SPIKE_LOOKBACKS,
    add_spike_breakout_features,
    enrich_spike_breakout_sources,
    feature_columns as spike_breakout_feature_columns,
    source_columns as spike_breakout_source_columns,
)
from regression_feature_engineering.features.structural_room import (  # noqa: E402
    DEFAULT_ROOM_LOOKBACKS,
    add_structural_room_features,
    enrich_structural_room_sources,
    feature_columns as structural_room_feature_columns,
    source_columns as structural_room_source_columns,
)
from regression_feature_engineering.features.temporal_memory_transforms import (  # noqa: E402
    DEFAULT_MEMORY_DIFF_LAGS,
    DEFAULT_MEMORY_EWM_SPANS,
    DEFAULT_MEMORY_LAGS,
    DEFAULT_MEMORY_RANK_WINDOWS,
    TemporalMemoryState,
    feature_columns as temporal_memory_feature_columns,
    parse_positive_ints,
    selected_source_columns as temporal_memory_source_columns,
)
from regression_feature_engineering.features.unsupervised_factor_layer import (  # noqa: E402
    DEFAULT_FACTOR_LOOKBACKS,
    add_unsupervised_factor_layer_features,
    feature_columns as unsupervised_factor_feature_columns,
    required_component_families as unsupervised_factor_required_families,
)
from regression_feature_engineering.features.volatility_state import (  # noqa: E402
    DEFAULT_VOL_LOOKBACKS,
    add_volatility_state_features,
    feature_columns as volatility_feature_columns,
)
from scripts.feature_engineering.htf_asset_registry import normalize_htf_asset_id  # noqa: E402
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (  # noqa: E402
    STAGE1_MULTIASSET_ROOT_LAYOUTS,
    parse_stage1_target_assets,
)
from scripts.project_paths import ensure_project_root_on_path  # noqa: E402


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
DEFAULT_FAMILIES = ("foundation_alignment", "volatility_state")
IDENTITY_COLUMNS = ("timestamp", "batch_id", "asset_id", "root_id", "feature_set")
IMPLEMENTED_MATERIALIZER_FAMILIES = (
    "foundation_alignment",
    "volatility_state",
    "structural_room",
    "acceptance_persistence",
    "rejection_chop",
    "spike_breakout",
    "liquidity_volume_pressure",
    "regime_calendar_state",
    "interaction_confluence",
    "cross_asset_context",
    "temporal_memory_transforms",
    "unsupervised_factor_layer",
    "sequence_embedding_layer",
)


@dataclass(frozen=True)
class MaterializedFeatureRoot:
    """Summary of one generated regression feature root."""

    asset_id: str
    root_key: str
    root_id: str
    output_dir: Path
    rows: int
    feature_count: int
    duplicate_count: int
    null_feature_count: int
    families: tuple[str, ...]
    timeframes: tuple[str, ...]


def parse_families(raw: str | tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    """Parse requested feature families in registry phase order."""

    registry = feature_family_registry()
    known = {item.family_id: item for item in registry}
    if raw is None:
        selected = DEFAULT_FAMILIES
    elif isinstance(raw, str):
        selected = tuple(part.strip() for part in raw.split(",") if part.strip())
    else:
        selected = tuple(str(part).strip() for part in raw if str(part).strip())
    unknown = [family for family in selected if family not in known]
    if unknown:
        raise ValueError(f"Unknown feature family/families {unknown}; known={sorted(known)}")
    unsupported = [family for family in selected if family not in IMPLEMENTED_MATERIALIZER_FAMILIES]
    if unsupported:
        raise ValueError(
            "Feature family/families are planned but not implemented in the materializer yet: "
            f"{unsupported}. Implement the family module and materializer branch before requesting it."
        )
    return tuple(item.family_id for item in registry if item.family_id in set(selected))


def parse_lookbacks(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse positive integer lookback windows."""

    if raw is None:
        values = DEFAULT_VOL_LOOKBACKS
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError("Lookbacks must be positive integers")
    return values


def parse_room_lookbacks(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse structural-room positive integer lookback windows."""

    if raw is None:
        values = DEFAULT_ROOM_LOOKBACKS
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError("Structural room lookbacks must be positive integers")
    return values


def parse_accept_lookbacks(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse acceptance/persistence positive integer lookback windows."""

    if raw is None:
        values = DEFAULT_ACCEPT_LOOKBACKS
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError("Acceptance/persistence lookbacks must be positive integers")
    return values


def parse_chop_lookbacks(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse rejection/chop positive integer lookback windows."""

    if raw is None:
        values = DEFAULT_CHOP_LOOKBACKS
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError("Rejection/chop lookbacks must be positive integers")
    return values


def parse_spike_lookbacks(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse spike/breakout positive integer lookback windows."""

    if raw is None:
        values = DEFAULT_SPIKE_LOOKBACKS
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError("Spike/breakout lookbacks must be positive integers")
    return values


def parse_liq_lookbacks(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse liquidity/volume-pressure positive integer lookback windows."""

    if raw is None:
        values = DEFAULT_LIQ_LOOKBACKS
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError("Liquidity/volume-pressure lookbacks must be positive integers")
    return values


def parse_regime_lookbacks(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse regime/calendar positive integer lookback windows."""

    if raw is None:
        values = DEFAULT_REGIME_LOOKBACKS
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError("Regime/calendar lookbacks must be positive integers")
    return values


def parse_confluence_lookbacks(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse interaction/confluence positive integer lookback windows."""

    if raw is None:
        values = DEFAULT_CONFLUENCE_LOOKBACKS
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError("Interaction/confluence lookbacks must be positive integers")
    return values


def parse_xasset_lookbacks(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse cross-asset positive integer lookback windows."""

    if raw is None:
        values = DEFAULT_XASSET_LOOKBACKS
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError("Cross-asset lookbacks must be positive integers")
    return values


def parse_factor_lookbacks(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse unsupervised/factor positive integer lookback parameters."""

    if raw is None:
        values = DEFAULT_FACTOR_LOOKBACKS
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError("Unsupervised/factor lookbacks must be positive integers")
    return tuple(dict.fromkeys(values))


def parse_sequence_lookbacks(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse sequence embedding positive integer lookback parameters."""

    if raw is None:
        values = DEFAULT_SEQUENCE_LOOKBACKS
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError("Sequence embedding lookbacks must be positive integers")
    return tuple(dict.fromkeys(values))


def parse_xasset_context_assets(raw: str | tuple[str, ...] | list[str] | None, *, target_asset: str) -> tuple[str, ...]:
    """Resolve cross-asset context peers for one target asset."""

    target_asset = normalize_htf_asset_id(target_asset)
    if raw is None or (isinstance(raw, str) and raw.strip().lower() == "auto"):
        return DEFAULT_CROSS_ASSET_PEERS.get(target_asset, ())
    if isinstance(raw, str):
        if raw.strip() == "":
            return ()
        values = tuple(part.strip() for part in raw.split(",") if part.strip())
    else:
        values = tuple(str(value).strip() for value in raw if str(value).strip())
    normalized = tuple(normalize_htf_asset_id(value) for value in values)
    return tuple(asset for asset in normalized if asset != target_asset)


def parse_memory_lags(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse temporal-memory lag parameters."""

    return parse_positive_ints(raw, default=DEFAULT_MEMORY_LAGS, name="Memory lags")


def parse_memory_ewm_spans(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse temporal-memory EWM span parameters."""

    return parse_positive_ints(raw, default=DEFAULT_MEMORY_EWM_SPANS, name="Memory EWM spans")


def parse_memory_rank_windows(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse temporal-memory rank-position windows."""

    return parse_positive_ints(raw, default=DEFAULT_MEMORY_RANK_WINDOWS, name="Memory rank windows")


def parse_memory_diff_lags(raw: str | tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    """Parse temporal-memory difference lag parameters."""

    return parse_positive_ints(raw, default=DEFAULT_MEMORY_DIFF_LAGS, name="Memory diff lags")


def materialize_regression_feature_roots(
    *,
    project_root: Path,
    assets: tuple[str, ...],
    roots: tuple[str, ...],
    families: tuple[str, ...] = DEFAULT_FAMILIES,
    timeframes: tuple[str, ...] = DEFAULT_TIMEFRAMES,
    lookbacks: tuple[int, ...] = DEFAULT_VOL_LOOKBACKS,
    room_lookbacks: tuple[int, ...] = DEFAULT_ROOM_LOOKBACKS,
    accept_lookbacks: tuple[int, ...] = DEFAULT_ACCEPT_LOOKBACKS,
    chop_lookbacks: tuple[int, ...] = DEFAULT_CHOP_LOOKBACKS,
    spike_lookbacks: tuple[int, ...] = DEFAULT_SPIKE_LOOKBACKS,
    liq_lookbacks: tuple[int, ...] = DEFAULT_LIQ_LOOKBACKS,
    regime_lookbacks: tuple[int, ...] = DEFAULT_REGIME_LOOKBACKS,
    confluence_lookbacks: tuple[int, ...] = DEFAULT_CONFLUENCE_LOOKBACKS,
    xasset_lookbacks: tuple[int, ...] = DEFAULT_XASSET_LOOKBACKS,
    factor_lookbacks: tuple[int, ...] = DEFAULT_FACTOR_LOOKBACKS,
    sequence_lookbacks: tuple[int, ...] = DEFAULT_SEQUENCE_LOOKBACKS,
    xasset_context_assets: tuple[str, ...] | str | None = None,
    memory_lags: tuple[int, ...] = DEFAULT_MEMORY_LAGS,
    memory_ewm_spans: tuple[int, ...] = DEFAULT_MEMORY_EWM_SPANS,
    memory_rank_windows: tuple[int, ...] = DEFAULT_MEMORY_RANK_WINDOWS,
    memory_diff_lags: tuple[int, ...] = DEFAULT_MEMORY_DIFF_LAGS,
    batch_limit: int | None = None,
    batch_chunk_size: int = 64,
    dry_run: bool = False,
) -> list[MaterializedFeatureRoot]:
    """Materialize selected regression feature families for asset/root pairs."""

    data_root = project_root / "data"
    families = parse_families(families)
    timeframes = normalize_timeframes(timeframes)
    lookbacks = parse_lookbacks(lookbacks)
    room_lookbacks = parse_room_lookbacks(room_lookbacks)
    accept_lookbacks = parse_accept_lookbacks(accept_lookbacks)
    chop_lookbacks = parse_chop_lookbacks(chop_lookbacks)
    spike_lookbacks = parse_spike_lookbacks(spike_lookbacks)
    liq_lookbacks = parse_liq_lookbacks(liq_lookbacks)
    regime_lookbacks = parse_regime_lookbacks(regime_lookbacks)
    confluence_lookbacks = parse_confluence_lookbacks(confluence_lookbacks)
    xasset_lookbacks = parse_xasset_lookbacks(xasset_lookbacks)
    factor_lookbacks = parse_factor_lookbacks(factor_lookbacks)
    sequence_lookbacks = parse_sequence_lookbacks(sequence_lookbacks)
    memory_lags = parse_memory_lags(memory_lags)
    memory_ewm_spans = parse_memory_ewm_spans(memory_ewm_spans)
    memory_rank_windows = parse_memory_rank_windows(memory_rank_windows)
    memory_diff_lags = parse_memory_diff_lags(memory_diff_lags)
    if batch_chunk_size <= 0:
        raise ValueError("batch_chunk_size must be a positive integer")
    summaries: list[MaterializedFeatureRoot] = []
    for asset_id in assets:
        asset_id = normalize_htf_asset_id(asset_id)
        for root_key in roots:
            context_assets = parse_xasset_context_assets(xasset_context_assets, target_asset=asset_id)
            summaries.append(
                _materialize_one(
                    data_root=data_root,
                    asset_id=asset_id,
                    root_key=root_key,
                    families=families,
                    timeframes=timeframes,
                    lookbacks=lookbacks,
                    room_lookbacks=room_lookbacks,
                    accept_lookbacks=accept_lookbacks,
                    chop_lookbacks=chop_lookbacks,
                    spike_lookbacks=spike_lookbacks,
                    liq_lookbacks=liq_lookbacks,
                    regime_lookbacks=regime_lookbacks,
                    confluence_lookbacks=confluence_lookbacks,
                    xasset_lookbacks=xasset_lookbacks,
                    factor_lookbacks=factor_lookbacks,
                    sequence_lookbacks=sequence_lookbacks,
                    xasset_context_assets=context_assets,
                    memory_lags=memory_lags,
                    memory_ewm_spans=memory_ewm_spans,
                    memory_rank_windows=memory_rank_windows,
                    memory_diff_lags=memory_diff_lags,
                    batch_limit=batch_limit,
                    batch_chunk_size=int(batch_chunk_size),
                    dry_run=dry_run,
                )
            )
    return summaries


def _materialize_one(
    *,
    data_root: Path,
    asset_id: str,
    root_key: str,
    families: tuple[str, ...],
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...],
    room_lookbacks: tuple[int, ...],
    accept_lookbacks: tuple[int, ...],
    chop_lookbacks: tuple[int, ...],
    spike_lookbacks: tuple[int, ...],
    liq_lookbacks: tuple[int, ...],
    regime_lookbacks: tuple[int, ...],
    confluence_lookbacks: tuple[int, ...],
    xasset_lookbacks: tuple[int, ...],
    factor_lookbacks: tuple[int, ...],
    sequence_lookbacks: tuple[int, ...],
    xasset_context_assets: tuple[str, ...],
    memory_lags: tuple[int, ...],
    memory_ewm_spans: tuple[int, ...],
    memory_rank_windows: tuple[int, ...],
    memory_diff_lags: tuple[int, ...],
    batch_limit: int | None,
    batch_chunk_size: int,
    dry_run: bool,
) -> MaterializedFeatureRoot:
    layout = STAGE1_MULTIASSET_ROOT_LAYOUTS[root_key]
    label_dir = regression_label_root(data_root, asset_id, layout.label_root)
    output_dir = regression_feature_root(data_root, asset_id, layout.root_id)
    label_paths = sorted(label_dir.glob("batch_*.parquet"))
    if batch_limit is not None:
        label_paths = label_paths[: int(batch_limit)]
    if not label_paths:
        raise FileNotFoundError(f"No regression label batches found in {label_dir}")

    rows = _read_label_rows(label_paths, asset_id=asset_id, root_id=layout.root_id)
    bars_by_timeframe = _read_canonical_bars(data_root=data_root, asset_id=asset_id, timeframes=timeframes)

    feature_columns: list[str] = []
    catalog: list[dict[str, Any]] = []
    if "volatility_state" in families:
        feature_columns.extend(volatility_feature_columns(timeframes=timeframes, lookbacks=lookbacks))
        catalog.extend(_volatility_catalog(timeframes=timeframes, lookbacks=lookbacks))
    if "structural_room" in families:
        structural_bars = {
            timeframe: enrich_structural_room_sources(bars, lookbacks=room_lookbacks)
            for timeframe, bars in bars_by_timeframe.items()
        }
        feature_columns.extend(structural_room_feature_columns(timeframes=timeframes, lookbacks=room_lookbacks))
        catalog.extend(_structural_room_catalog(timeframes=timeframes, lookbacks=room_lookbacks))
    else:
        structural_bars = {}
    if "acceptance_persistence" in families:
        acceptance_bars = {
            timeframe: enrich_acceptance_persistence_sources(bars, lookbacks=accept_lookbacks)
            for timeframe, bars in bars_by_timeframe.items()
        }
        feature_columns.extend(acceptance_feature_columns(timeframes=timeframes, lookbacks=accept_lookbacks))
        catalog.extend(_acceptance_catalog(timeframes=timeframes, lookbacks=accept_lookbacks))
    else:
        acceptance_bars = {}
    if "rejection_chop" in families:
        chop_bars = {
            timeframe: enrich_rejection_chop_sources(bars, lookbacks=chop_lookbacks)
            for timeframe, bars in bars_by_timeframe.items()
        }
        feature_columns.extend(rejection_chop_feature_columns(timeframes=timeframes, lookbacks=chop_lookbacks))
        catalog.extend(_rejection_chop_catalog(timeframes=timeframes, lookbacks=chop_lookbacks))
    else:
        chop_bars = {}
    if "spike_breakout" in families:
        spike_bars = {
            timeframe: enrich_spike_breakout_sources(bars, lookbacks=spike_lookbacks)
            for timeframe, bars in bars_by_timeframe.items()
        }
        feature_columns.extend(spike_breakout_feature_columns(timeframes=timeframes, lookbacks=spike_lookbacks))
        catalog.extend(_spike_breakout_catalog(timeframes=timeframes, lookbacks=spike_lookbacks))
    else:
        spike_bars = {}
    if "liquidity_volume_pressure" in families:
        liquidity_bars = {
            timeframe: enrich_liquidity_volume_pressure_sources(bars, lookbacks=liq_lookbacks)
            for timeframe, bars in bars_by_timeframe.items()
        }
        feature_columns.extend(liquidity_feature_columns(timeframes=timeframes, lookbacks=liq_lookbacks))
        catalog.extend(_liquidity_volume_catalog(timeframes=timeframes, lookbacks=liq_lookbacks))
    else:
        liquidity_bars = {}
    if "regime_calendar_state" in families:
        regime_bars = {
            timeframe: enrich_regime_calendar_state_sources(bars, lookbacks=regime_lookbacks)
            for timeframe, bars in bars_by_timeframe.items()
        }
        feature_columns.extend(regime_calendar_feature_columns(timeframes=timeframes, lookbacks=regime_lookbacks))
        catalog.extend(_regime_calendar_catalog(timeframes=timeframes, lookbacks=regime_lookbacks))
    else:
        regime_bars = {}

    if "interaction_confluence" in families:
        missing_base = [
            family
            for family in (
                "structural_room",
                "acceptance_persistence",
                "rejection_chop",
                "spike_breakout",
                "liquidity_volume_pressure",
                "regime_calendar_state",
            )
            if family not in families
        ]
        if missing_base:
            raise ValueError(
                "interaction_confluence requires these causal component families: "
                f"{missing_base}. Request all component families before Phase 10."
            )
        feature_columns.extend(interaction_confluence_feature_columns(timeframes=timeframes, lookbacks=confluence_lookbacks))
        catalog.extend(_interaction_confluence_catalog(timeframes=timeframes, lookbacks=confluence_lookbacks))

    if "cross_asset_context" in families:
        if not xasset_context_assets:
            raise ValueError(
                f"cross_asset_context requested for {asset_id}, but no context peers were resolved. "
                "Pass --xasset-context-assets or add the asset to DEFAULT_CROSS_ASSET_PEERS."
            )
        xasset_pair_bars = _read_cross_asset_pair_bars(
            data_root=data_root,
            target_asset=asset_id,
            context_assets=xasset_context_assets,
            target_bars_by_timeframe=bars_by_timeframe,
            timeframes=timeframes,
            lookbacks=xasset_lookbacks,
        )
        feature_columns.extend(
            cross_asset_feature_columns(
                context_assets=xasset_context_assets,
                timeframes=timeframes,
                lookbacks=xasset_lookbacks,
            )
        )
        catalog.extend(
            _cross_asset_catalog(
                context_assets=xasset_context_assets,
                timeframes=timeframes,
                lookbacks=xasset_lookbacks,
            )
        )
    else:
        xasset_pair_bars = {}

    if "temporal_memory_transforms" in families:
        memory_sources = temporal_memory_source_columns(
            tuple(feature_columns),
            timeframes=timeframes,
            room_lookbacks=room_lookbacks,
            accept_lookbacks=accept_lookbacks,
        )
        if not memory_sources:
            raise ValueError(
                "temporal_memory_transforms requires at least one implemented base feature family "
                "such as volatility_state, structural_room, or acceptance_persistence."
            )
        memory_columns = temporal_memory_feature_columns(
            source_columns=memory_sources,
            lags=memory_lags,
            ewm_spans=memory_ewm_spans,
            rank_windows=memory_rank_windows,
            diff_lags=memory_diff_lags,
        )
        feature_columns.extend(memory_columns)
        catalog.extend(
            _temporal_memory_catalog(
                source_columns=memory_sources,
                lags=memory_lags,
                ewm_spans=memory_ewm_spans,
                rank_windows=memory_rank_windows,
                diff_lags=memory_diff_lags,
            )
        )
        memory_state: TemporalMemoryState | None = TemporalMemoryState(
            source_columns=memory_sources,
            lags=memory_lags,
            ewm_spans=memory_ewm_spans,
            rank_windows=memory_rank_windows,
            diff_lags=memory_diff_lags,
        )
    else:
        memory_state = None

    if "unsupervised_factor_layer" in families:
        missing_base = [family for family in unsupervised_factor_required_families() if family not in families]
        if missing_base:
            raise ValueError(
                "unsupervised_factor_layer requires these causal component families: "
                f"{missing_base}. Request all deterministic component families before Phase 12."
            )
        feature_columns.extend(unsupervised_factor_feature_columns(timeframes=timeframes, lookbacks=factor_lookbacks))
        catalog.extend(_unsupervised_factor_catalog(timeframes=timeframes, lookbacks=factor_lookbacks))

    if "sequence_embedding_layer" in families:
        if "unsupervised_factor_layer" not in families:
            raise ValueError("sequence_embedding_layer requires unsupervised_factor_layer in the same materialization run.")
        feature_columns.extend(sequence_embedding_feature_columns(lookbacks=sequence_lookbacks))
        catalog.extend(_sequence_embedding_catalog(timeframes=timeframes, lookbacks=sequence_lookbacks))

    if not dry_run:
        _prepare_output_root(output_dir)

    row_count = 0
    duplicate_count = 0
    null_feature_count = 0
    diagnostic_columns: tuple[str, ...] = ()
    output_schema: dict[str, pl.DataType] | None = None
    max_vol_overlap = max(lookbacks) if "volatility_state" in families and lookbacks else 0
    for chunk in _batch_chunks(rows, batch_chunk_size=batch_chunk_size):
        output = _build_feature_chunk(
            rows=rows,
            chunk_start=chunk[0],
            chunk_end=chunk[1],
            vol_overlap_rows=max_vol_overlap,
            bars_by_timeframe=bars_by_timeframe,
            structural_bars=structural_bars,
            acceptance_bars=acceptance_bars,
            chop_bars=chop_bars,
            spike_bars=spike_bars,
            liquidity_bars=liquidity_bars,
            regime_bars=regime_bars,
            xasset_pair_bars=xasset_pair_bars,
            xasset_context_assets=xasset_context_assets,
            families=families,
            timeframes=timeframes,
            lookbacks=lookbacks,
            room_lookbacks=room_lookbacks,
            accept_lookbacks=accept_lookbacks,
            chop_lookbacks=chop_lookbacks,
            spike_lookbacks=spike_lookbacks,
            liq_lookbacks=liq_lookbacks,
            regime_lookbacks=regime_lookbacks,
            confluence_lookbacks=confluence_lookbacks,
            xasset_lookbacks=xasset_lookbacks,
        )
        if memory_state is not None:
            output = output.hstack(memory_state.transform_frame(output))
        if "unsupervised_factor_layer" in families:
            output = add_unsupervised_factor_layer_features(
                output,
                timeframes=timeframes,
                lookbacks=factor_lookbacks,
                context_assets=xasset_context_assets,
            )
        if "sequence_embedding_layer" in families:
            output = add_sequence_embedding_layer_features(
                output,
                timeframes=timeframes,
                lookbacks=sequence_lookbacks,
            )
        if not diagnostic_columns:
            diagnostic_columns = tuple(_diagnostic_columns(output))
        if output_schema is None:
            output_schema = output.schema
        row_count += output.height
        duplicate_count += int(output.select(["timestamp", "batch_id"]).height - output.select(["timestamp", "batch_id"]).unique().height)
        if feature_columns:
            null_feature_count += int(
                output.select(pl.sum_horizontal([pl.col(col).is_null().cast(pl.Int64) for col in feature_columns]).sum()).item()
            )
        if not dry_run:
            _write_batch_files(output, output_dir)
        del output
        gc.collect()

    summary = MaterializedFeatureRoot(
        asset_id=asset_id,
        root_key=root_key,
        root_id=layout.root_id,
        output_dir=output_dir,
        rows=row_count,
        feature_count=len(feature_columns),
        duplicate_count=int(duplicate_count),
        null_feature_count=null_feature_count,
        families=families,
        timeframes=timeframes,
    )
    if not dry_run:
        if output_schema is None:
            raise RuntimeError("No output chunks were produced")
        _write_output_metadata(
            output_dir=output_dir,
            summary=summary,
            feature_columns=tuple(feature_columns),
            diagnostic_columns=diagnostic_columns,
            catalog=catalog,
            output_schema=output_schema,
            source_paths=[*label_paths, *[canonical_ohlcv_path(data_root, asset_id, tf) for tf in timeframes]],
        )
    return summary


def _read_label_rows(paths: list[Path], *, asset_id: str, root_id: str) -> pl.DataFrame:
    required = {
        "timestamp",
        "batch_id",
        "close",
        "tb_volatility_pct",
        "tb_atr_pct_14",
        "tb_realized_vol_120",
    }
    schema = pl.read_parquet(paths[0], n_rows=0).schema
    missing = required - set(schema)
    if missing:
        raise ValueError(f"Regression label rows missing source columns: {sorted(missing)}")
    return (
        pl.read_parquet([str(path) for path in paths])
        .select(
            [
                "timestamp",
                "batch_id",
                "close",
                "tb_volatility_pct",
                "tb_atr_pct_14",
                "tb_realized_vol_120",
            ]
        )
        .sort(["batch_id", "timestamp"])
        .with_columns(
            [
                pl.lit(asset_id).alias("asset_id"),
                pl.lit(root_id).alias("root_id"),
                pl.lit(FEATURE_SET).alias("feature_set"),
            ]
        )
    )


def _read_canonical_bars(
    *,
    data_root: Path,
    asset_id: str,
    timeframes: tuple[str, ...],
) -> dict[str, pl.DataFrame]:
    bars: dict[str, pl.DataFrame] = {}
    for timeframe in timeframes:
        path = canonical_ohlcv_path(data_root, asset_id, timeframe)
        if not path.exists():
            raise FileNotFoundError(f"Canonical {timeframe} OHLCV not found: {path}")
        bars[timeframe] = pl.read_parquet(path).sort("timestamp")
    return bars


def _read_cross_asset_pair_bars(
    *,
    data_root: Path,
    target_asset: str,
    context_assets: tuple[str, ...],
    target_bars_by_timeframe: dict[str, pl.DataFrame],
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...],
) -> dict[str, dict[str, pl.DataFrame]]:
    """Read context canonical bars and build exact-match pair source bars."""

    out: dict[str, dict[str, pl.DataFrame]] = {}
    for context_asset in context_assets:
        context_asset = normalize_htf_asset_id(context_asset)
        context_bars = _read_canonical_bars(data_root=data_root, asset_id=context_asset, timeframes=timeframes)
        out[context_asset] = {
            timeframe: build_cross_asset_pair_sources(
                target_bars_by_timeframe[timeframe],
                context_bars[timeframe],
                context_asset=context_asset,
                lookbacks=lookbacks,
            )
            for timeframe in timeframes
        }
        del context_bars
    return out


def _batch_chunks(rows: pl.DataFrame, *, batch_chunk_size: int) -> list[tuple[int, int]]:
    """Return row-index chunks containing whole `batch_id` groups."""

    if rows.height == 0:
        return []
    batch_ids = rows.get_column("batch_id")
    boundaries: list[tuple[int, int]] = []
    start = 0
    for idx in range(1, rows.height):
        if batch_ids[idx] != batch_ids[start]:
            boundaries.append((start, idx))
            start = idx
    boundaries.append((start, rows.height))

    chunks: list[tuple[int, int]] = []
    for idx in range(0, len(boundaries), int(batch_chunk_size)):
        selected = boundaries[idx : idx + int(batch_chunk_size)]
        chunks.append((selected[0][0], selected[-1][1]))
    return chunks


def _build_feature_chunk(
    *,
    rows: pl.DataFrame,
    chunk_start: int,
    chunk_end: int,
    vol_overlap_rows: int,
    bars_by_timeframe: dict[str, pl.DataFrame],
    structural_bars: dict[str, pl.DataFrame],
    acceptance_bars: dict[str, pl.DataFrame],
    chop_bars: dict[str, pl.DataFrame],
    spike_bars: dict[str, pl.DataFrame],
    liquidity_bars: dict[str, pl.DataFrame],
    regime_bars: dict[str, pl.DataFrame],
    xasset_pair_bars: dict[str, dict[str, pl.DataFrame]],
    xasset_context_assets: tuple[str, ...],
    families: tuple[str, ...],
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...],
    room_lookbacks: tuple[int, ...],
    accept_lookbacks: tuple[int, ...],
    chop_lookbacks: tuple[int, ...],
    spike_lookbacks: tuple[int, ...],
    liq_lookbacks: tuple[int, ...],
    regime_lookbacks: tuple[int, ...],
    confluence_lookbacks: tuple[int, ...],
    xasset_lookbacks: tuple[int, ...],
) -> pl.DataFrame:
    """Build one output chunk using only final model-facing feature columns."""

    chunk_len = int(chunk_end - chunk_start)
    chunk_rows = rows.slice(chunk_start, chunk_len)
    diagnostic_frame = join_all_closed_bar_context(
        chunk_rows,
        bars_by_timeframe,
        timeframes=timeframes,
        include_source_ohlcv=False,
    )
    output = diagnostic_frame.select([*IDENTITY_COLUMNS, *_diagnostic_columns(diagnostic_frame)])
    del diagnostic_frame

    if "volatility_state" in families:
        context_start = max(0, int(chunk_start) - int(vol_overlap_rows))
        context_rows = rows.slice(context_start, int(chunk_end) - context_start)
        output_offset = int(chunk_start) - context_start
        aligned = join_all_closed_bar_context(
            context_rows,
            bars_by_timeframe,
            timeframes=timeframes,
            include_source_ohlcv=True,
            source_columns=OHLCV_COLUMNS,
        )
        aligned = add_volatility_state_features(aligned, timeframes=timeframes, lookbacks=lookbacks)
        family_columns = volatility_feature_columns(timeframes=timeframes, lookbacks=lookbacks)
        output = output.hstack(aligned.select(family_columns).slice(output_offset, chunk_len))
        del aligned
        del context_rows

    if "structural_room" in families:
        aligned = join_all_closed_bar_context(
            chunk_rows,
            structural_bars,
            timeframes=timeframes,
            include_source_ohlcv=True,
            source_columns=structural_room_source_columns(lookbacks=room_lookbacks),
        )
        aligned = add_structural_room_features(aligned, timeframes=timeframes, lookbacks=room_lookbacks)
        family_columns = structural_room_feature_columns(timeframes=timeframes, lookbacks=room_lookbacks)
        output = output.hstack(aligned.select(family_columns))
        del aligned

    if "acceptance_persistence" in families:
        acceptance_source = tuple(dict.fromkeys(("open", "close", *acceptance_source_columns(lookbacks=accept_lookbacks))))
        aligned = join_all_closed_bar_context(
            chunk_rows,
            acceptance_bars,
            timeframes=timeframes,
            include_source_ohlcv=True,
            source_columns=acceptance_source,
        )
        aligned = add_acceptance_persistence_features(aligned, timeframes=timeframes, lookbacks=accept_lookbacks)
        family_columns = acceptance_feature_columns(timeframes=timeframes, lookbacks=accept_lookbacks)
        output = output.hstack(aligned.select(family_columns))
        del aligned

    if "rejection_chop" in families:
        aligned = join_all_closed_bar_context(
            chunk_rows,
            chop_bars,
            timeframes=timeframes,
            include_source_ohlcv=True,
            source_columns=rejection_chop_source_columns(lookbacks=chop_lookbacks),
        )
        aligned = add_rejection_chop_features(aligned, timeframes=timeframes, lookbacks=chop_lookbacks)
        family_columns = rejection_chop_feature_columns(timeframes=timeframes, lookbacks=chop_lookbacks)
        output = output.hstack(aligned.select(family_columns))
        del aligned

    if "spike_breakout" in families:
        aligned = join_all_closed_bar_context(
            chunk_rows,
            spike_bars,
            timeframes=timeframes,
            include_source_ohlcv=True,
            source_columns=spike_breakout_source_columns(lookbacks=spike_lookbacks),
        )
        aligned = add_spike_breakout_features(aligned, timeframes=timeframes, lookbacks=spike_lookbacks)
        family_columns = spike_breakout_feature_columns(timeframes=timeframes, lookbacks=spike_lookbacks)
        output = output.hstack(aligned.select(family_columns))
        del aligned

    if "liquidity_volume_pressure" in families:
        aligned = join_all_closed_bar_context(
            chunk_rows,
            liquidity_bars,
            timeframes=timeframes,
            include_source_ohlcv=True,
            source_columns=liquidity_source_columns(lookbacks=liq_lookbacks),
        )
        aligned = add_liquidity_volume_pressure_features(aligned, timeframes=timeframes, lookbacks=liq_lookbacks)
        family_columns = liquidity_feature_columns(timeframes=timeframes, lookbacks=liq_lookbacks)
        output = output.hstack(aligned.select(family_columns))
        del aligned

    if "regime_calendar_state" in families:
        aligned = join_all_closed_bar_context(
            chunk_rows,
            regime_bars,
            timeframes=timeframes,
            include_source_ohlcv=True,
            source_columns=regime_calendar_source_columns(lookbacks=regime_lookbacks),
        )
        aligned = add_regime_calendar_state_features(aligned, timeframes=timeframes, lookbacks=regime_lookbacks)
        family_columns = regime_calendar_feature_columns(timeframes=timeframes, lookbacks=regime_lookbacks)
        output = output.hstack(aligned.select(family_columns))
        del aligned

    if "interaction_confluence" in families:
        output = add_interaction_confluence_features(
            output,
            timeframes=timeframes,
            lookbacks=confluence_lookbacks,
        )

    if "cross_asset_context" in families:
        for context_asset in xasset_context_assets:
            if context_asset not in xasset_pair_bars:
                raise KeyError(f"Missing cross-asset pair bars for context asset {context_asset}")
            aligned = join_all_closed_bar_context(
                chunk_rows,
                xasset_pair_bars[context_asset],
                timeframes=timeframes,
                include_source_ohlcv=True,
                source_columns=cross_asset_source_columns(lookbacks=xasset_lookbacks),
            )
            aligned = add_cross_asset_context_features(
                aligned,
                context_asset=context_asset,
                timeframes=timeframes,
                lookbacks=xasset_lookbacks,
            )
            family_columns = cross_asset_feature_columns(
                context_assets=(context_asset,),
                timeframes=timeframes,
                lookbacks=xasset_lookbacks,
            )
            output = output.hstack(aligned.select(family_columns))
            del aligned

    return output


def _diagnostic_columns(df: pl.DataFrame) -> list[str]:
    return [
        col
        for col in df.columns
        if col.startswith("rpf_align_")
        and (col.endswith("_bar_open_ts") or col.endswith("_bar_close_ts") or col.endswith("_has_closed_bar"))
    ]


def _volatility_catalog(*, timeframes: tuple[str, ...], lookbacks: tuple[int, ...]) -> list[dict[str, Any]]:
    definitions: list[FeatureDefinition] = [
        FeatureDefinition(
            name="rpf_vol_atr_std_dominance_bnd",
            family="volatility_state",
            target_intent=("all_targets", "denominator_quality"),
            source_timeframes=("1m",),
            source_columns=("tb_atr_pct_14", "tb_realized_vol_120"),
            availability="prediction_time",
            normalization="bounded_signed",
        ),
        FeatureDefinition(
            name="rpf_vol_atr_std_log_ratio",
            family="volatility_state",
            target_intent=("all_targets", "denominator_quality"),
            source_timeframes=("1m",),
            source_columns=("tb_atr_pct_14", "tb_realized_vol_120"),
            availability="prediction_time",
            normalization="log_ratio",
        ),
    ]
    for lookback in lookbacks:
        for suffix, normalization in (
            ("z", "rolling_past_zscore_clipped"),
            ("rel_median", "rolling_past_median_ratio"),
            ("chg", "past_percent_change"),
        ):
            definitions.append(
                FeatureDefinition(
                    name=f"rpf_vol_tb_vol_{suffix}_l{lookback}",
                    family="volatility_state",
                    target_intent=("all_targets", "volatility_state"),
                    source_timeframes=("1m",),
                    source_columns=("tb_volatility_pct",),
                    availability="prediction_time_with_prior_rolling_window",
                    normalization=normalization,
                )
            )
    for timeframe in timeframes:
        for suffix, normalization in (
            ("range_to_tb_vol", "bounded_positive_volatility_units"),
            ("abs_ret_to_tb_vol", "bounded_positive_volatility_units"),
            ("range_efficiency_bnd", "bounded_ratio"),
        ):
            definitions.append(
                FeatureDefinition(
                    name=f"rpf_vol_{timeframe}_{suffix}",
                    family="volatility_state",
                    target_intent=("all_targets", "closed_bar_volatility_context"),
                    source_timeframes=(timeframe,),
                    source_columns=("open", "high", "low", "close"),
                    availability="closed_bar_asof_only",
                    normalization=normalization,
                )
            )
    return [asdict(item) for item in definitions]


def _structural_room_catalog(*, timeframes: tuple[str, ...], lookbacks: tuple[int, ...]) -> list[dict[str, Any]]:
    definitions: list[FeatureDefinition] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            for suffix, intent, normalization in (
                ("up_to_high", ("up_extreme", "upside_room"), "bounded_positive_volatility_units"),
                ("down_to_low", ("down_extreme", "downside_room"), "bounded_positive_volatility_units"),
                ("asym", ("up_down_asymmetry",), "bounded_signed"),
                ("up_room_share", ("up_down_asymmetry", "upside_room_share"), "bounded_0_1"),
                ("room_balance", ("up_down_asymmetry", "signed_room_balance"), "bounded_signed_volatility_units"),
                ("donchian_pos", ("price_location",), "bounded_0_1"),
                ("breakout_above", ("up_extreme", "prior_high_breakout"), "bounded_positive_volatility_units"),
                ("breakdown_below", ("down_extreme", "prior_low_breakdown"), "bounded_positive_volatility_units"),
                ("break_balance", ("up_down_asymmetry", "signed_breakout_balance"), "bounded_signed_volatility_units"),
                ("value_dist", ("price_location", "value_distance"), "bounded_signed_volatility_units"),
            ):
                name = (
                    f"rpf_room_{timeframe}_{suffix}_l{lookback}_vol"
                    if suffix not in {"asym", "up_room_share", "donchian_pos"}
                    else f"rpf_room_{timeframe}_{suffix}_l{lookback}_bnd"
                )
                definitions.append(
                    FeatureDefinition(
                        name=name,
                        family="structural_room",
                        target_intent=tuple(intent),
                        source_timeframes=(timeframe,),
                        source_columns=("open", "high", "low", "close", "volume"),
                        availability="previous_closed_channel_asof_only",
                        normalization=normalization,
                    )
                )
    return [asdict(item) for item in definitions]


def _acceptance_catalog(*, timeframes: tuple[str, ...], lookbacks: tuple[int, ...]) -> list[dict[str, Any]]:
    definitions: list[FeatureDefinition] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            for suffix, intent, normalization in (
                ("close_loc_avg", ("up_mean_high", "down_mean_low", "close_location"), "bounded_0_1"),
                ("close_loc_balance", ("directional_acceptance",), "bounded_signed"),
                ("body_persist", ("directional_pressure", "body_persistence"), "bounded_signed"),
                ("return_persist", ("directional_pressure", "return_persistence"), "bounded_signed"),
                ("above_value_share", ("up_mean_high", "accepted_above_value"), "bounded_0_1"),
                ("below_value_share", ("down_mean_low", "accepted_below_value"), "bounded_0_1"),
                ("value_accept_balance", ("directional_acceptance",), "bounded_signed"),
                ("value_dist", ("value_distance", "acceptance_context"), "bounded_signed_volatility_units"),
                ("trend_eff", ("up_mean_high", "down_mean_low", "path_persistence"), "bounded_signed"),
                ("up_pullback_shallow", ("up_mean_high", "shallow_pullback"), "bounded_0_1"),
                ("down_pullback_shallow", ("down_mean_low", "shallow_pullback"), "bounded_0_1"),
            ):
                name = (
                    f"rpf_accept_{timeframe}_{suffix}_l{lookback}_vol"
                    if suffix == "value_dist"
                    else f"rpf_accept_{timeframe}_{suffix}_l{lookback}_bnd"
                )
                definitions.append(
                    FeatureDefinition(
                        name=name,
                        family="acceptance_persistence",
                        target_intent=tuple(intent),
                        source_timeframes=(timeframe,),
                        source_columns=("open", "high", "low", "close", "volume"),
                        availability="closed_bar_asof_only",
                        normalization=normalization,
                    )
                )
    for name, intent in (
        ("rpf_accept_tf_bull_agreement_share_bnd", ("up_mean_high", "higher_timeframe_alignment")),
        ("rpf_accept_tf_bear_agreement_share_bnd", ("down_mean_low", "higher_timeframe_alignment")),
        ("rpf_accept_tf_direction_agreement_bnd", ("directional_acceptance", "higher_timeframe_alignment")),
    ):
        definitions.append(
            FeatureDefinition(
                name=name,
                family="acceptance_persistence",
                target_intent=tuple(intent),
                source_timeframes=timeframes,
                source_columns=("open", "close"),
                availability="closed_bar_asof_only",
                normalization="bounded_signed",
            )
        )
    return [asdict(item) for item in definitions]


def _rejection_chop_catalog(*, timeframes: tuple[str, ...], lookbacks: tuple[int, ...]) -> list[dict[str, Any]]:
    """Build catalog entries for rejection/chop features."""

    definitions: list[FeatureDefinition] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            for suffix, intent, normalization in (
                ("upper_reject", ("up_extreme", "up_mean_high", "upper_wick_rejection"), "bounded_0_1"),
                ("lower_reject", ("down_extreme", "down_mean_low", "lower_wick_rejection"), "bounded_0_1"),
                ("reject_balance", ("directional_rejection_balance",), "bounded_signed"),
                ("two_sided", ("all_targets", "two_sided_chop"), "bounded_0_1"),
                ("reversal_rate", ("all_targets", "path_reversal_frequency"), "bounded_0_1"),
                ("path_eff", ("up_mean_high", "down_mean_low", "path_efficiency"), "bounded_0_1"),
                ("path_chop", ("all_targets", "inefficient_path_chop"), "bounded_0_1"),
                ("failed_up_break", ("up_extreme", "failed_upside_breakout"), "bounded_0_1"),
                ("failed_down_break", ("down_extreme", "failed_downside_breakdown"), "bounded_0_1"),
                ("failed_break_balance", ("directional_failed_break_balance",), "bounded_signed"),
            ):
                definitions.append(
                    FeatureDefinition(
                        name=f"rpf_chop_{timeframe}_{suffix}_l{lookback}_bnd",
                        family="rejection_chop",
                        target_intent=tuple(intent),
                        source_timeframes=(timeframe,),
                        source_columns=("open", "high", "low", "close"),
                        availability="closed_bar_asof_only",
                        normalization=normalization,
                    )
                )
    return [asdict(item) for item in definitions]


def _spike_breakout_catalog(*, timeframes: tuple[str, ...], lookbacks: tuple[int, ...]) -> list[dict[str, Any]]:
    """Build catalog entries for spike/breakout features."""

    definitions: list[FeatureDefinition] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            for suffix, intent, normalization in (
                ("up_break_prox", ("up_extreme", "upside_breakout_proximity"), "bounded_positive_volatility_units"),
                ("down_break_prox", ("down_extreme", "downside_breakdown_proximity"), "bounded_positive_volatility_units"),
                ("break_prox_balance", ("up_down_asymmetry", "breakout_proximity_balance"), "bounded_signed_volatility_units"),
                ("up_breakout", ("up_extreme", "active_upside_breakout"), "bounded_positive_volatility_units"),
                ("down_breakdown", ("down_extreme", "active_downside_breakdown"), "bounded_positive_volatility_units"),
                ("breakout_balance", ("up_down_asymmetry", "active_breakout_balance"), "bounded_signed_volatility_units"),
                ("squeeze", ("all_targets", "volatility_compression"), "bounded_0_1"),
                ("release", ("up_extreme", "down_extreme", "range_release"), "bounded_0_1"),
                ("squeeze_release", ("up_extreme", "down_extreme", "compression_release"), "bounded_0_1"),
                ("up_impulse", ("up_extreme", "upside_impulse"), "bounded_0_1"),
                ("down_impulse", ("down_extreme", "downside_impulse"), "bounded_0_1"),
                ("impulse_balance", ("up_down_asymmetry", "one_sided_impulse"), "bounded_signed"),
                ("up_volume_impulse", ("up_extreme", "volume_confirmed_upside_impulse"), "bounded_0_1"),
                ("down_volume_impulse", ("down_extreme", "volume_confirmed_downside_impulse"), "bounded_0_1"),
                ("volume_impulse_balance", ("up_down_asymmetry", "volume_confirmed_impulse_balance"), "bounded_signed"),
                ("tail_asym", ("up_down_asymmetry", "tail_risk_asymmetry"), "bounded_signed"),
            ):
                name = (
                    f"rpf_spike_{timeframe}_{suffix}_l{lookback}_vol"
                    if suffix
                    in {
                        "up_break_prox",
                        "down_break_prox",
                        "break_prox_balance",
                        "up_breakout",
                        "down_breakdown",
                        "breakout_balance",
                    }
                    else f"rpf_spike_{timeframe}_{suffix}_l{lookback}_bnd"
                )
                definitions.append(
                    FeatureDefinition(
                        name=name,
                        family="spike_breakout",
                        target_intent=tuple(intent),
                        source_timeframes=(timeframe,),
                        source_columns=("open", "high", "low", "close", "volume"),
                        availability="previous_closed_levels_or_closed_bar_asof_only",
                        normalization=normalization,
                    )
                )
    return [asdict(item) for item in definitions]


def _liquidity_volume_catalog(*, timeframes: tuple[str, ...], lookbacks: tuple[int, ...]) -> list[dict[str, Any]]:
    """Build catalog entries for liquidity/volume-pressure features."""

    definitions: list[FeatureDefinition] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            for suffix, intent, normalization in (
                ("volume_z", ("participation", "volume_unusualness"), "rolling_past_zscore_clipped"),
                ("dollar_volume_rel", ("liquidity_state", "turnover_proxy"), "bounded_relative_median_ratio"),
                ("volume_wakeup", ("volume_wakeup", "compression_release_confirmation"), "bounded_confluence"),
                ("up_volume_share", ("up_mean_high", "up_extreme", "buy_pressure_share"), "bounded_0_1"),
                ("down_volume_share", ("down_mean_low", "down_extreme", "sell_pressure_share"), "bounded_0_1"),
                ("volume_pressure_balance", ("directional_volume_pressure",), "bounded_signed"),
                ("obv_slope", ("directional_volume_pressure", "obv_proxy"), "bounded_signed"),
                ("money_flow_balance", ("acceptance", "money_flow_proxy"), "bounded_signed"),
                ("zero_volume_share", ("session_asset_behavior", "synthetic_or_no_trade_context"), "bounded_0_1"),
            ):
                name = (
                    f"rpf_liq_{timeframe}_{suffix}_l{lookback}"
                    if suffix == "volume_z"
                    else f"rpf_liq_{timeframe}_{suffix}_l{lookback}_bnd"
                )
                definitions.append(
                    FeatureDefinition(
                        name=name,
                        family="liquidity_volume_pressure",
                        target_intent=tuple(intent),
                        source_timeframes=(timeframe,),
                        source_columns=("open", "high", "low", "close", "volume"),
                        availability="closed_bar_asof_only",
                        normalization=normalization,
                    )
                )
    return [asdict(item) for item in definitions]


def _regime_calendar_catalog(*, timeframes: tuple[str, ...], lookbacks: tuple[int, ...]) -> list[dict[str, Any]]:
    """Build catalog entries for regime/calendar features."""

    definitions: list[FeatureDefinition] = [
        FeatureDefinition(
            name="rpf_regime_utc_hour_sin",
            family="regime_calendar_state",
            target_intent=("known_calendar_state", "intraday_cycle"),
            source_timeframes=("1m",),
            source_columns=("timestamp",),
            availability="known_at_prediction_time",
            normalization="cyclic_sine",
        ),
        FeatureDefinition(
            name="rpf_regime_utc_hour_cos",
            family="regime_calendar_state",
            target_intent=("known_calendar_state", "intraday_cycle"),
            source_timeframes=("1m",),
            source_columns=("timestamp",),
            availability="known_at_prediction_time",
            normalization="cyclic_cosine",
        ),
        FeatureDefinition(
            name="rpf_regime_utc_dow_sin",
            family="regime_calendar_state",
            target_intent=("known_calendar_state", "weekday_cycle"),
            source_timeframes=("1m",),
            source_columns=("timestamp",),
            availability="known_at_prediction_time",
            normalization="cyclic_sine",
        ),
        FeatureDefinition(
            name="rpf_regime_utc_dow_cos",
            family="regime_calendar_state",
            target_intent=("known_calendar_state", "weekday_cycle"),
            source_timeframes=("1m",),
            source_columns=("timestamp",),
            availability="known_at_prediction_time",
            normalization="cyclic_cosine",
        ),
        FeatureDefinition(
            name="rpf_regime_utc_is_weekend_bnd",
            family="regime_calendar_state",
            target_intent=("known_calendar_state", "crypto_weekend_or_session_gap_context"),
            source_timeframes=("1m",),
            source_columns=("timestamp",),
            availability="known_at_prediction_time",
            normalization="binary_flag",
        ),
    ]
    for timeframe in timeframes:
        for suffix, intent, normalization in (
            ("market_open", ("session_state", "market_open"), "binary_flag"),
            ("synthetic_no_trade", ("session_state", "synthetic_no_trade"), "binary_flag"),
            ("gap_fill", ("session_state", "gap_fill"), "binary_flag"),
            ("minutes_since_prev_real_bar", ("session_state", "gap_or_stale_context"), "bounded_ratio"),
            ("session_progress", ("session_state", "session_progress"), "bounded_ratio"),
            ("minutes_to_close", ("session_state", "closing_proximity"), "bounded_ratio"),
            ("session_open", ("session_state", "open_bar"), "binary_flag"),
            ("session_close", ("session_state", "close_bar"), "binary_flag"),
            ("weekly_open", ("calendar_state", "weekly_open"), "binary_flag"),
            ("weekly_close", ("calendar_state", "weekly_close"), "binary_flag"),
        ):
            definitions.append(
                FeatureDefinition(
                    name=f"rpf_regime_{timeframe}_{suffix}_bnd",
                    family="regime_calendar_state",
                    target_intent=tuple(intent),
                    source_timeframes=(timeframe,),
                    source_columns=("canonical_session_metadata",),
                    availability="latest_closed_bar_metadata_asof_only",
                    normalization=normalization,
                )
            )
        for lookback in lookbacks:
            for suffix, intent, normalization in (
                ("vol_rel", ("volatility_regime", "range_expansion"), "bounded_relative_ratio"),
                ("vol_expanding", ("volatility_regime", "expansion_flag"), "binary_flag"),
                ("trend_eff", ("trend_range_regime", "trend_efficiency"), "bounded_signed"),
                ("trend_sign", ("trend_range_regime", "directional_persistence"), "bounded_signed"),
                ("trend_alignment", ("trend_range_regime", "signed_alignment"), "bounded_signed"),
                ("range_chop", ("trend_range_regime", "range_or_chop"), "bounded_0_1"),
                ("bull_trend", ("trend_range_regime", "bullish_trend_flag"), "binary_flag"),
                ("bear_trend", ("trend_range_regime", "bearish_trend_flag"), "binary_flag"),
            ):
                definitions.append(
                    FeatureDefinition(
                        name=f"rpf_regime_{timeframe}_{suffix}_l{lookback}_bnd",
                        family="regime_calendar_state",
                        target_intent=tuple(intent),
                        source_timeframes=(timeframe,),
                        source_columns=("open", "high", "low", "close", "canonical_session_metadata"),
                        availability="closed_bar_asof_only",
                        normalization=normalization,
                    )
                )
    return [asdict(item) for item in definitions]


def _temporal_memory_catalog(
    *,
    source_columns: tuple[str, ...],
    lags: tuple[int, ...],
    ewm_spans: tuple[int, ...],
    rank_windows: tuple[int, ...],
    diff_lags: tuple[int, ...],
) -> list[dict[str, Any]]:
    """Build catalog entries for temporal-memory transforms."""

    definitions: list[FeatureDefinition] = []
    for source in source_columns:
        slug = source.removeprefix("rpf_")
        for lag in lags:
            definitions.append(
                FeatureDefinition(
                    name=f"rpf_mem_{slug}_lag{lag}",
                    family="temporal_memory_transforms",
                    target_intent=("lags", "prior_feature_state"),
                    source_timeframes=("derived",),
                    source_columns=(source,),
                    availability="prior_rows_only_streaming_state",
                    normalization="same_as_source",
                )
            )
        for span in ewm_spans:
            for suffix, intent, normalization in (
                ("", ("ewm_state",), "same_as_source_smoothed"),
                ("_slope", ("ewm_slope", "state_change"), "same_as_source_delta"),
                ("_resid", ("ewm_residual", "recent_deviation"), "same_as_source_delta"),
            ):
                definitions.append(
                    FeatureDefinition(
                        name=f"rpf_mem_{slug}_ewm{span}{suffix}",
                        family="temporal_memory_transforms",
                        target_intent=tuple(intent),
                        source_timeframes=("derived",),
                        source_columns=(source,),
                        availability="prior_rows_only_streaming_state",
                        normalization=normalization,
                    )
                )
        for window in rank_windows:
            definitions.append(
                FeatureDefinition(
                    name=f"rpf_mem_{slug}_rankpos{window}_bnd",
                    family="temporal_memory_transforms",
                    target_intent=("percentile_rank_position", "recent_unusualness"),
                    source_timeframes=("derived",),
                    source_columns=(source,),
                    availability="prior_rows_only_streaming_state",
                    normalization="bounded_0_1_recent_minmax_position",
                )
            )
        for lag in diff_lags:
            for suffix, intent in (
                (f"diff{lag}", ("first_difference", "slope")),
                (f"diff2_{lag}", ("second_difference", "acceleration")),
            ):
                definitions.append(
                    FeatureDefinition(
                        name=f"rpf_mem_{slug}_{suffix}",
                        family="temporal_memory_transforms",
                        target_intent=tuple(intent),
                        source_timeframes=("derived",),
                        source_columns=(source,),
                        availability="prior_rows_only_streaming_state",
                        normalization="same_as_source_delta",
                    )
                )
    return [asdict(item) for item in definitions]


def _interaction_confluence_catalog(*, timeframes: tuple[str, ...], lookbacks: tuple[int, ...]) -> list[dict[str, Any]]:
    """Build catalog entries for interaction/confluence features."""

    definitions: list[FeatureDefinition] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            for suffix, intent, normalization in (
                ("up_squeeze_break", ("up_extreme", "compression_breakout_confluence"), "bounded_0_1"),
                ("down_squeeze_break", ("down_extreme", "compression_breakdown_confluence"), "bounded_0_1"),
                ("squeeze_break_balance", ("up_down_asymmetry", "compression_break_balance"), "bounded_signed"),
                ("up_trend_accept", ("up_mean_high", "trend_acceptance_confluence"), "bounded_0_1"),
                ("down_trend_accept", ("down_mean_low", "trend_acceptance_confluence"), "bounded_0_1"),
                ("trend_accept_balance", ("up_down_asymmetry", "trend_acceptance_balance"), "bounded_signed"),
                ("up_volume_impulse", ("up_extreme", "volume_confirmed_impulse"), "bounded_0_1"),
                ("down_volume_impulse", ("down_extreme", "volume_confirmed_impulse"), "bounded_0_1"),
                ("volume_impulse_balance", ("up_down_asymmetry", "volume_impulse_balance"), "bounded_signed"),
                ("up_clean_persist", ("up_mean_high", "chop_filtered_persistence"), "bounded_0_1"),
                ("down_clean_persist", ("down_mean_low", "chop_filtered_persistence"), "bounded_0_1"),
                ("clean_persist_balance", ("up_down_asymmetry", "clean_persistence_balance"), "bounded_signed"),
                ("up_room_pressure", ("up_extreme", "upside_room_with_pressure"), "bounded_0_1"),
                ("down_room_pressure", ("down_extreme", "downside_room_with_pressure"), "bounded_0_1"),
                ("room_pressure_balance", ("up_down_asymmetry", "room_pressure_balance"), "bounded_signed"),
            ):
                definitions.append(
                    FeatureDefinition(
                        name=f"rpf_conf_{timeframe}_{suffix}_l{lookback}_bnd",
                        family="interaction_confluence",
                        target_intent=tuple(intent),
                        source_timeframes=(timeframe,),
                        source_columns=("validated_rpf_component_features",),
                        availability="derived_from_causal_component_features",
                        normalization=normalization,
                    )
                )
    return [asdict(item) for item in definitions]


def _cross_asset_catalog(
    *,
    context_assets: tuple[str, ...],
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...],
) -> list[dict[str, Any]]:
    """Build catalog entries for deterministic cross-asset context features."""

    definitions: list[FeatureDefinition] = []
    for context_asset in context_assets:
        slug = context_asset.lower()
        for timeframe in timeframes:
            for lookback in lookbacks:
                for suffix, intent, normalization in (
                    ("ret_spread", ("relative_pressure", "return_spread"), "bounded_signed"),
                    ("rel_strength", ("relative_strength", "relative_movement_size"), "bounded_signed"),
                    ("range_spread", ("relative_volatility", "range_spread"), "bounded_signed"),
                    ("corr", ("common_risk_state", "rolling_correlation"), "bounded_signed"),
                    ("context_pressure", ("context_directional_pressure",), "bounded_signed"),
                    ("common_direction", ("common_direction_agreement",), "bounded_signed"),
                    ("context_range_share", ("context_volatility_share",), "bounded_0_1"),
                    ("volume_rel_spread", ("relative_participation",), "bounded_signed"),
                ):
                    definitions.append(
                        FeatureDefinition(
                            name=f"rpf_xasset_{slug}_{timeframe}_{suffix}_l{lookback}_bnd",
                            family="cross_asset_context",
                            target_intent=tuple(intent),
                            source_timeframes=(timeframe,),
                            source_columns=(f"{context_asset}_canonical_ohlcv", "target_canonical_ohlcv"),
                            availability="exact_timestamp_pair_bar_then_closed_bar_asof",
                            normalization=normalization,
                        )
                    )
    return [asdict(item) for item in definitions]


def _unsupervised_factor_catalog(*, timeframes: tuple[str, ...], lookbacks: tuple[int, ...]) -> list[dict[str, Any]]:
    """Build catalog entries for deterministic factor-proxy features."""

    definitions: list[FeatureDefinition] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            for suffix, intent, normalization in (
                ("path_width", ("path_regime", "total_path_width_proxy"), "bounded_0_1"),
                ("direction", ("up_down_asymmetry", "directional_pressure_factor"), "bounded_signed"),
                ("persistence", ("up_mean_high", "down_mean_low", "persistence_factor"), "bounded_signed"),
                ("shock", ("up_extreme", "down_extreme", "shock_or_release_factor"), "bounded_0_1"),
                ("rejection", ("rejection", "failed_break_factor"), "bounded_signed"),
                ("context", ("relative_pressure", "cross_asset_factor"), "bounded_signed"),
                ("anomaly", ("path_regime", "unusual_state_proxy"), "bounded_0_1"),
                ("clean_direction", ("directional_pressure", "chop_filtered_factor"), "bounded_signed"),
            ):
                definitions.append(
                    FeatureDefinition(
                        name=f"rpf_factor_{timeframe}_{suffix}_l{lookback}_bnd",
                        family="unsupervised_factor_layer",
                        target_intent=tuple(intent),
                        source_timeframes=(timeframe,),
                        source_columns=("validated_rpf_component_features",),
                        availability="derived_from_causal_component_features_no_global_fit",
                        normalization=normalization,
                    )
                )
    return [asdict(item) for item in definitions]


def _sequence_embedding_catalog(*, timeframes: tuple[str, ...], lookbacks: tuple[int, ...]) -> list[dict[str, Any]]:
    """Build catalog entries for deterministic sequence-shape features."""

    definitions: list[FeatureDefinition] = []
    for lookback in lookbacks:
        for suffix, intent, normalization in (
            ("direction_mean", ("sequence_shape", "multi_timeframe_direction"), "bounded_signed"),
            ("direction_slope", ("sequence_shape", "short_long_direction_slope"), "bounded_signed"),
            ("direction_dispersion", ("sequence_shape", "direction_disagreement"), "bounded_0_1"),
            ("direction_consensus", ("sequence_shape", "direction_consensus"), "bounded_signed"),
            ("width_mean", ("sequence_shape", "multi_timeframe_width"), "bounded_0_1"),
            ("width_slope", ("sequence_shape", "short_long_width_slope"), "bounded_signed"),
            ("width_dispersion", ("sequence_shape", "width_disagreement"), "bounded_0_1"),
            ("shock_mean", ("sequence_shape", "multi_timeframe_shock"), "bounded_0_1"),
            ("persistence_mean", ("sequence_shape", "multi_timeframe_persistence"), "bounded_signed"),
            ("clean_direction", ("sequence_shape", "clean_direction_stack"), "bounded_signed"),
        ):
            definitions.append(
                FeatureDefinition(
                    name=f"rpf_seq_{suffix}_l{lookback}_bnd",
                    family="sequence_embedding_layer",
                    target_intent=tuple(intent),
                    source_timeframes=timeframes,
                    source_columns=("rpf_factor_*",),
                    availability="derived_from_causal_factor_proxies_no_encoder_fit",
                    normalization=normalization,
                )
            )
    return [asdict(item) for item in definitions]


def _write_output_root(
    output: pl.DataFrame,
    *,
    output_dir: Path,
    summary: MaterializedFeatureRoot,
    feature_columns: tuple[str, ...],
    diagnostic_columns: tuple[str, ...],
    catalog: list[dict[str, Any]],
    source_paths: list[Path],
) -> None:
    _prepare_output_root(output_dir)
    _write_batch_files(output, output_dir)
    _write_output_metadata(
        output_dir=output_dir,
        summary=summary,
        feature_columns=feature_columns,
        diagnostic_columns=diagnostic_columns,
        catalog=catalog,
        output_schema=output.schema,
        source_paths=source_paths,
    )


def _prepare_output_root(output_dir: Path) -> None:
    """Prepare an output root for a complete rewrite."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("batch_*.parquet"):
        stale.unlink()
    for stale_name in ("manifest.json", "feature_catalog.json"):
        stale = output_dir / stale_name
        if stale.exists():
            stale.unlink()


def _write_output_metadata(
    *,
    output_dir: Path,
    summary: MaterializedFeatureRoot,
    feature_columns: tuple[str, ...],
    diagnostic_columns: tuple[str, ...],
    catalog: list[dict[str, Any]],
    output_schema: dict[str, pl.DataType],
    source_paths: list[Path],
) -> None:
    """Write manifest/catalog after all batch files are written."""

    schema_repr = json.dumps({name: str(dtype) for name, dtype in output_schema.items()}, sort_keys=True)
    source_repr = json.dumps([str(path) for path in source_paths], sort_keys=True)
    manifest = {
        "feature_set": FEATURE_SET,
        "target_variant": TARGET_VARIANT,
        "asset": summary.asset_id,
        "root_key": summary.root_key,
        "root_id": summary.root_id,
        "families": list(summary.families),
        "timeframes": list(summary.timeframes),
        "row_count": summary.rows,
        "feature_count": summary.feature_count,
        "feature_columns": list(feature_columns),
        "diagnostic_columns": list(diagnostic_columns),
        "duplicate_count": summary.duplicate_count,
        "null_feature_count": summary.null_feature_count,
        "schema_hash": hashlib.sha256(schema_repr.encode()).hexdigest(),
        "source_fingerprint": hashlib.sha256(source_repr.encode()).hexdigest(),
        "source_paths": [str(path) for path in source_paths],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (output_dir / "feature_catalog.json").write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n")


def _write_batch_files(output: pl.DataFrame, output_dir: Path) -> None:
    """Write contiguous batch slices without materializing all partitions."""

    batch_ids = output.get_column("batch_id")
    row_count = output.height
    start = 0
    while start < row_count:
        key = int(batch_ids[start])
        end = start + 1
        while end < row_count and int(batch_ids[end]) == key:
            end += 1
        output.slice(start, end - start).write_parquet(output_dir / f"batch_{key:04d}.parquet")
        start = end


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize regression path features.")
    parser.add_argument("--assets", default="BTCUSDT")
    parser.add_argument("--roots", nargs="*", default=["8h/B"], choices=sorted(STAGE1_MULTIASSET_ROOT_LAYOUTS))
    parser.add_argument("--families", default=",".join(DEFAULT_FAMILIES))
    parser.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES))
    parser.add_argument("--vol-lookbacks", default=",".join(str(value) for value in DEFAULT_VOL_LOOKBACKS))
    parser.add_argument("--room-lookbacks", default=",".join(str(value) for value in DEFAULT_ROOM_LOOKBACKS))
    parser.add_argument("--accept-lookbacks", default=",".join(str(value) for value in DEFAULT_ACCEPT_LOOKBACKS))
    parser.add_argument("--chop-lookbacks", default=",".join(str(value) for value in DEFAULT_CHOP_LOOKBACKS))
    parser.add_argument("--spike-lookbacks", default=",".join(str(value) for value in DEFAULT_SPIKE_LOOKBACKS))
    parser.add_argument("--liq-lookbacks", default=",".join(str(value) for value in DEFAULT_LIQ_LOOKBACKS))
    parser.add_argument("--regime-lookbacks", default=",".join(str(value) for value in DEFAULT_REGIME_LOOKBACKS))
    parser.add_argument("--confluence-lookbacks", default=",".join(str(value) for value in DEFAULT_CONFLUENCE_LOOKBACKS))
    parser.add_argument("--xasset-lookbacks", default=",".join(str(value) for value in DEFAULT_XASSET_LOOKBACKS))
    parser.add_argument("--factor-lookbacks", default=",".join(str(value) for value in DEFAULT_FACTOR_LOOKBACKS))
    parser.add_argument("--sequence-lookbacks", default=",".join(str(value) for value in DEFAULT_SEQUENCE_LOOKBACKS))
    parser.add_argument(
        "--xasset-context-assets",
        default="auto",
        help="Comma-separated cross-asset peers, empty for none, or auto for default peer map.",
    )
    parser.add_argument("--memory-lags", default=",".join(str(value) for value in DEFAULT_MEMORY_LAGS))
    parser.add_argument("--memory-ewm-spans", default=",".join(str(value) for value in DEFAULT_MEMORY_EWM_SPANS))
    parser.add_argument("--memory-rank-windows", default=",".join(str(value) for value in DEFAULT_MEMORY_RANK_WINDOWS))
    parser.add_argument("--memory-diff-lags", default=",".join(str(value) for value in DEFAULT_MEMORY_DIFF_LAGS))
    parser.add_argument("--batch-limit", type=int, default=None)
    parser.add_argument("--batch-chunk-size", type=int, default=64)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _ = load_config()
    results = materialize_regression_feature_roots(
        project_root=PROJECT_ROOT,
        assets=parse_stage1_target_assets(args.assets),
        roots=tuple(args.roots),
        families=parse_families(args.families),
        timeframes=normalize_timeframes(args.timeframes),
        lookbacks=parse_lookbacks(args.vol_lookbacks),
        room_lookbacks=parse_room_lookbacks(args.room_lookbacks),
        accept_lookbacks=parse_accept_lookbacks(args.accept_lookbacks),
        chop_lookbacks=parse_chop_lookbacks(args.chop_lookbacks),
        spike_lookbacks=parse_spike_lookbacks(args.spike_lookbacks),
        liq_lookbacks=parse_liq_lookbacks(args.liq_lookbacks),
        regime_lookbacks=parse_regime_lookbacks(args.regime_lookbacks),
        confluence_lookbacks=parse_confluence_lookbacks(args.confluence_lookbacks),
        xasset_lookbacks=parse_xasset_lookbacks(args.xasset_lookbacks),
        factor_lookbacks=parse_factor_lookbacks(args.factor_lookbacks),
        sequence_lookbacks=parse_sequence_lookbacks(args.sequence_lookbacks),
        xasset_context_assets=args.xasset_context_assets,
        memory_lags=parse_memory_lags(args.memory_lags),
        memory_ewm_spans=parse_memory_ewm_spans(args.memory_ewm_spans),
        memory_rank_windows=parse_memory_rank_windows(args.memory_rank_windows),
        memory_diff_lags=parse_memory_diff_lags(args.memory_diff_lags),
        batch_limit=args.batch_limit,
        batch_chunk_size=int(args.batch_chunk_size),
        dry_run=bool(args.dry_run),
    )
    for result in results:
        print(
            f"{result.asset_id} {result.root_key} {FEATURE_SET}: "
            f"rows={result.rows:,} features={result.feature_count:,} "
            f"duplicates={result.duplicate_count:,} null_features={result.null_feature_count:,} "
            f"output={result.output_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
