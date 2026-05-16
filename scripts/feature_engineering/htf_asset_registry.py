"""Asset registry for the multi-asset HTF materialization workflow.

This module is the single place where HTF asset ids are mapped to provider raw
roots, canonical calendar ids, provider priority, and auxiliary-source support.
The pipeline should ask this registry for asset metadata instead of hardcoding
paths or symbol slugs in feature/label code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.feature_engineering.htf_trading_calendar import (
    CALENDAR_CRYPTO_24_7,
    CALENDAR_FUTURES_SESSION_OBSERVED,
)


CORE_HTF_ASSET_IDS = (
    "BTCUSDT",
    "ETHUSDT",
    "EURUSD",
    "USDJPY",
    "GC",
    "CL",
    "ES",
    "NQ",
)


@dataclass(frozen=True)
class HTFRawFileGroup:
    """One provider-specific raw file group for an HTF asset/timeframe."""

    provider: str
    root_dir: str
    dir_template: str
    file_patterns: tuple[str, ...]
    priority: int

    def directory(self, project_root: Path, tf: str) -> Path:
        """Return the provider directory for a project root and timeframe."""
        return project_root / self.root_dir / self.dir_template.format(tf=tf)

    def files(self, project_root: Path, tf: str, slug: str) -> list[Path]:
        """Return sorted parquet files matching this group for an asset slug."""
        directory = self.directory(project_root, tf)
        if not directory.exists():
            return []

        matched: list[Path] = []
        for pattern in self.file_patterns:
            matched.extend(
                sorted(directory.glob(pattern.format(tf=tf, symbol=slug, slug=slug)))
            )
        return sorted(set(matched), key=lambda path: str(path))


@dataclass(frozen=True)
class HTFAssetSpec:
    """Minimal asset contract needed by the shared HTF materialization pipeline."""

    asset_id: str
    slug: str
    source_kind: str
    calendar_id: str
    raw_file_groups: tuple[HTFRawFileGroup, ...]
    use_auxiliary_sources: bool

    def groups_for_timeframe(self, tf: str) -> tuple[HTFRawFileGroup, ...]:
        # Current groups are timeframe-template based, so all groups apply to
        # every upstream HTF timeframe.
        return self.raw_file_groups


def _bybit_crypto(asset_id: str) -> HTFAssetSpec:
    slug = asset_id.lower()
    return HTFAssetSpec(
        asset_id=asset_id,
        slug=slug,
        source_kind="bybit_crypto",
        calendar_id=CALENDAR_CRYPTO_24_7,
        raw_file_groups=(
            HTFRawFileGroup(
                provider="bybit",
                root_dir="fetchingByBit",
                dir_template="sorted-{tf}-bybit-linear",
                file_patterns=(
                    "{symbol}_linear_sorted_batch_*.parquet",
                    "{symbol}_{tf}.parquet",
                ),
                priority=10,
            ),
        ),
        use_auxiliary_sources=True,
    )


def _multiasset_future(asset_id: str) -> HTFAssetSpec:
    slug = asset_id.lower()
    return HTFAssetSpec(
        asset_id=asset_id,
        slug=slug,
        source_kind="multiasset_ohlcv",
        calendar_id=CALENDAR_FUTURES_SESSION_OBSERVED,
        raw_file_groups=(
            HTFRawFileGroup(
                provider="databento",
                root_dir="fetchingMultiAsset",
                dir_template="sorted-{tf}-databento-futures",
                file_patterns=("{symbol}_databento_sorted_batch_*.parquet",),
                priority=10,
            ),
            HTFRawFileGroup(
                provider="yfinance",
                root_dir="fetchingMultiAsset",
                dir_template="sorted-{tf}-yfinance-futures",
                file_patterns=("{symbol}_yfinance_sorted_batch_*.parquet",),
                priority=20,
            ),
        ),
        use_auxiliary_sources=False,
    )


HTF_ASSET_SPECS: dict[str, HTFAssetSpec] = {
    "BTCUSDT": _bybit_crypto("BTCUSDT"),
    "ETHUSDT": _bybit_crypto("ETHUSDT"),
    "EURUSD": _multiasset_future("EURUSD"),
    "USDJPY": _multiasset_future("USDJPY"),
    "GC": _multiasset_future("GC"),
    "CL": _multiasset_future("CL"),
    "ES": _multiasset_future("ES"),
    "NQ": _multiasset_future("NQ"),
}


def normalize_htf_asset_id(asset_id: str) -> str:
    """Normalize and validate user-provided HTF asset ids."""
    normalized = asset_id.strip().upper()
    if not normalized:
        raise ValueError("HTF asset id cannot be empty")
    if normalized not in HTF_ASSET_SPECS:
        known = ", ".join(CORE_HTF_ASSET_IDS)
        raise ValueError(f"Unknown HTF asset id: {asset_id!r}. Known assets: {known}")
    return normalized


def get_htf_asset_spec(asset_id: str) -> HTFAssetSpec:
    """Return the registry contract for one supported HTF asset."""
    return HTF_ASSET_SPECS[normalize_htf_asset_id(asset_id)]


def htf_asset_ids_from_csv(raw: str | None) -> tuple[str, ...]:
    """Parse `HTF_ASSETS` style input into validated asset ids."""
    if raw is None or raw.strip() == "":
        return ("BTCUSDT",)
    if raw.strip().lower() == "core":
        return CORE_HTF_ASSET_IDS
    return tuple(normalize_htf_asset_id(part) for part in raw.split(",") if part.strip())
