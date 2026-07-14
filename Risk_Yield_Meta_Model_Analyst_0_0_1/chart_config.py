"""Configuration for the local Lightweight Charts inspection workspace."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ANALYST_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ANALYST_ROOT.parent
WEB_ROOT = ANALYST_ROOT / "web"
WEB_DATA_ROOT = WEB_ROOT / "data"
DEFAULT_PAYLOAD_PATH = WEB_DATA_ROOT / "current.json"

BYBIT_ASSETS = ("BTCUSDT", "ETHUSDT")
MULTIASSET_ASSETS = ("CL", "ES", "EURUSD", "GC", "NQ", "USDJPY")
CORE_ASSETS = BYBIT_ASSETS + MULTIASSET_ASSETS

# Chart display increments follow the canonical instrument quotation units.
# They control visual formatting only; execution simulators retain their own
# explicit fill/cost contracts and never round orders through this mapping.
ASSET_PRICE_FORMATS = {
    "BTCUSDT": {"precision": 1, "min_move": 0.1},
    "ETHUSDT": {"precision": 2, "min_move": 0.01},
    "CL": {"precision": 2, "min_move": 0.01},
    "ES": {"precision": 2, "min_move": 0.25},
    "EURUSD": {"precision": 5, "min_move": 0.00001},
    "GC": {"precision": 1, "min_move": 0.1},
    "NQ": {"precision": 2, "min_move": 0.25},
    "USDJPY": {"precision": 3, "min_move": 0.001},
}

RAW_BYBIT_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")
RAW_MULTIASSET_TIMEFRAMES = ("1m", "15m")
CANONICAL_TIMEFRAMES = ("1m", "15m", "1h", "4h", "8h", "12h", "1d")

RAW_SOURCE = "raw"
CANONICAL_SOURCE = "canonical"
RAW_YFINANCE_SOURCE = "raw_yfinance"
RAW_TWELVEDATA_SOURCE = "raw_twelvedata"
RAW_DATABENTO_ES_BACKUP_SOURCE = "raw_databento_es_backup"

SOURCE_CHOICES = (
    CANONICAL_SOURCE,
    RAW_SOURCE,
    RAW_YFINANCE_SOURCE,
    RAW_TWELVEDATA_SOURCE,
    RAW_DATABENTO_ES_BACKUP_SOURCE,
)

SOURCE_LABELS = {
    CANONICAL_SOURCE: "Canonical OHLCV (main)",
    RAW_SOURCE: "Raw primary (debug)",
    RAW_YFINANCE_SOURCE: "Raw yfinance fallback (debug)",
    RAW_TWELVEDATA_SOURCE: "Raw TwelveData fallback (debug)",
    RAW_DATABENTO_ES_BACKUP_SOURCE: "Raw Databento ES backup (debug)",
}

DEFAULT_MAX_BARS = 5_000
HARD_MAX_BARS = 50_000
_TIMEFRAME_PATTERN = re.compile(r"^([1-9]\d*)([mhd])$")

# The catalog is an API/UI discovery contract.  Indicator implementations live
# in chart_export.py; keeping their stable IDs here lets the manifest describe
# every independently toggleable layer without introducing an import cycle.
CHART_INDICATOR_CATALOG = (
    {"id": "cusum_trend", "label": "CUSUM Trend", "group": "signal"},
    {"id": "ewma_volatility", "label": "EWMA Volatility", "group": "risk"},
    {
        "id": "volatility_scaled_trend",
        "label": "Volatility-Scaled Trend",
        "group": "signal",
    },
    {"id": "online_regime", "label": "Prototype Regime", "group": "regime"},
    {
        "id": "cross_timeframe_context",
        "label": "Cross-Timeframe Context",
        "group": "context",
    },
    {"id": "prior_structure", "label": "Prior Structure", "group": "context"},
    {
        "id": "comparable_volatility",
        "label": "Comparable Volatility",
        "group": "context",
    },
    {
        "id": "phase_adjusted_participation",
        "label": "Phase-Adjusted Participation",
        "group": "context",
    },
)


@dataclass(frozen=True)
class SourceResolution:
    """Resolved parquet files for one chart export request."""

    asset: str
    timeframe: str
    source: str
    provider: str
    files: tuple[Path, ...]
    source_root: Path
    description: str


def normalize_asset(asset: str) -> str:
    normalized = asset.strip().upper()
    if normalized not in CORE_ASSETS:
        known = ", ".join(CORE_ASSETS)
        raise ValueError(f"Unknown asset {asset!r}. Known assets: {known}")
    return normalized


def asset_price_format(asset: str) -> dict[str, float | int]:
    """Return the canonical chart display precision for an instrument."""

    return dict(ASSET_PRICE_FORMATS[normalize_asset(asset)])


def normalize_timeframe(timeframe: str) -> str:
    return timeframe.strip().lower()


def timeframe_seconds(timeframe: str) -> int:
    """Parse a positive minute/hour/day timeframe into nominal seconds."""

    value = normalize_timeframe(timeframe)
    match = _TIMEFRAME_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"Unsupported timeframe duration: {timeframe!r}")
    amount = int(match.group(1))
    multiplier = {"m": 60, "h": 3600, "d": 86400}[match.group(2)]
    return amount * multiplier


def normalize_source(source: str) -> str:
    normalized = source.strip().lower()
    if normalized not in SOURCE_CHOICES:
        known = ", ".join(SOURCE_CHOICES)
        raise ValueError(f"Unknown source {source!r}. Known sources: {known}")
    return normalized


def supported_timeframes(asset: str, source: str) -> tuple[str, ...]:
    asset = normalize_asset(asset)
    source = normalize_source(source)
    if source == CANONICAL_SOURCE:
        return CANONICAL_TIMEFRAMES
    if source == RAW_SOURCE:
        return (
            RAW_BYBIT_TIMEFRAMES if asset in BYBIT_ASSETS else RAW_MULTIASSET_TIMEFRAMES
        )
    if source in {
        RAW_YFINANCE_SOURCE,
        RAW_TWELVEDATA_SOURCE,
        RAW_DATABENTO_ES_BACKUP_SOURCE,
    }:
        return RAW_MULTIASSET_TIMEFRAMES
    raise AssertionError(f"Unhandled source: {source}")


def resolve_ohlcv_files(
    asset: str,
    timeframe: str,
    source: str = RAW_SOURCE,
) -> SourceResolution:
    """Resolve parquet files for one asset/timeframe/source selection."""

    asset = normalize_asset(asset)
    timeframe = normalize_timeframe(timeframe)
    source = normalize_source(source)

    allowed_timeframes = supported_timeframes(asset, source)
    if timeframe not in allowed_timeframes:
        allowed = ", ".join(allowed_timeframes)
        raise ValueError(
            f"{source!r} source for {asset} does not support timeframe "
            f"{timeframe!r}. Allowed: {allowed}"
        )

    slug = asset.lower()

    if source == CANONICAL_SOURCE:
        directory = (
            PROJECT_ROOT
            / "data"
            / "htf_multiasset"
            / slug
            / "htf_canonical_ohlcv"
            / timeframe
        )
        files = tuple(sorted(directory.glob(f"{slug}_{timeframe}_canonical.parquet")))
        provider = "canonical"
        description = "Processed canonical OHLCV from the HTF materialization pipeline."
    elif source == RAW_SOURCE and asset in BYBIT_ASSETS:
        directory = PROJECT_ROOT / "fetchingByBit" / f"sorted-{timeframe}-bybit-linear"
        files = tuple(sorted(directory.glob(f"{slug}_linear_sorted_batch_*.parquet")))
        provider = "bybit"
        description = "Raw Bybit linear trade OHLCV parquet batches."
    elif source == RAW_SOURCE:
        directory = (
            PROJECT_ROOT
            / "fetchingMultiAsset"
            / f"sorted-{timeframe}-databento-futures"
        )
        files = tuple(
            sorted(directory.glob(f"{slug}_databento_sorted_batch_*.parquet"))
        )
        provider = "databento"
        description = "Primary raw multi-asset OHLCV parquet batches."
    elif source == RAW_YFINANCE_SOURCE:
        directory = (
            PROJECT_ROOT / "fetchingMultiAsset" / f"sorted-{timeframe}-yfinance-futures"
        )
        files = tuple(sorted(directory.glob(f"{slug}_yfinance_sorted_batch_*.parquet")))
        provider = "yfinance"
        description = "Partial/fallback yfinance OHLCV parquet batches."
    elif source == RAW_TWELVEDATA_SOURCE:
        directory = (
            PROJECT_ROOT / "fetchingMultiAsset" / f"sorted-{timeframe}-twelvedata-multi"
        )
        files = tuple(
            sorted(directory.glob(f"{slug}_twelvedata_sorted_batch_*.parquet"))
        )
        provider = "twelvedata"
        description = "Partial/fallback TwelveData OHLCV parquet batches."
    elif source == RAW_DATABENTO_ES_BACKUP_SOURCE:
        if asset != "ES":
            raise ValueError("The Databento ES backup source only contains ES.")
        directory = (
            PROJECT_ROOT
            / "fetchingMultiAsset"
            / f"sorted-{timeframe}-databento-futures_es_backup_before_2021_backfill"
        )
        files = tuple(
            sorted(directory.glob(f"{slug}_databento_sorted_batch_*.parquet"))
        )
        provider = "databento_es_backup"
        description = "Backup ES Databento OHLCV snapshot."
    else:
        raise AssertionError(f"Unhandled source: {source}")

    if not files:
        raise FileNotFoundError(
            f"No parquet files found for asset={asset}, timeframe={timeframe}, "
            f"source={source} in {directory}"
        )

    return SourceResolution(
        asset=asset,
        timeframe=timeframe,
        source=source,
        provider=provider,
        files=files,
        source_root=directory,
        description=description,
    )


@lru_cache(maxsize=1)
def build_chart_manifest() -> dict[str, object]:
    """Return available chart selections for the browser UI."""

    assets = []
    for asset in CORE_ASSETS:
        source_entries = []
        for source in SOURCE_CHOICES:
            timeframe_entries = []
            for timeframe in supported_timeframes(asset, source):
                try:
                    resolution = resolve_ohlcv_files(
                        asset=asset,
                        timeframe=timeframe,
                        source=source,
                    )
                except (FileNotFoundError, ValueError):
                    continue
                timeframe_entries.append(
                    {
                        "timeframe": timeframe,
                        "provider": resolution.provider,
                        "sourcePathCount": len(resolution.files),
                        "sourceRoot": str(
                            resolution.source_root.relative_to(PROJECT_ROOT)
                        ),
                        "onlineSignals": {
                            "available": True,
                            "minimumClosedBarsForComposite": 193,
                            "persistentLiveReplay": source == CANONICAL_SOURCE,
                            "mode": (
                                "bounded_selection_stream_replay"
                                if source == CANONICAL_SOURCE
                                else "bounded_request_replay"
                            ),
                        },
                        "marketContext": {
                            "available": True,
                            "diagnosticOnly": True,
                            "availability": "post_close_usable_next_bar",
                            "phaseReferenceOccurrences": 20,
                            "calendarQualityMetadata": source == CANONICAL_SOURCE,
                        },
                        "minuteReplay": {
                            "available": source == CANONICAL_SOURCE,
                            "sourceTimeframe": "1m",
                            "signalFinality": "scheduled_target_bucket_end",
                            "execution": "next_real_1m_open",
                            "signalVintage": "current_canonical_replay",
                        },
                    }
                )
            if timeframe_entries:
                source_entries.append(
                    {
                        "source": source,
                        "label": SOURCE_LABELS[source],
                        "timeframes": timeframe_entries,
                    }
                )
        if source_entries:
            assets.append(
                {
                    "asset": asset,
                    "priceFormat": asset_price_format(asset),
                    "sources": source_entries,
                }
            )

    canonical_selection_count = sum(
        len(source_entry["timeframes"])
        for asset_entry in assets
        for source_entry in asset_entry["sources"]
        if source_entry["source"] == CANONICAL_SOURCE
    )

    return {
        "defaults": {
            "asset": "BTCUSDT",
            "source": CANONICAL_SOURCE,
            "timeframe": "1h",
            "maxBars": DEFAULT_MAX_BARS,
            "indicators": [entry["id"] for entry in CHART_INDICATOR_CATALOG],
        },
        "limits": {
            "defaultMaxBars": DEFAULT_MAX_BARS,
            "hardMaxBars": HARD_MAX_BARS,
        },
        "indicators": [dict(entry) for entry in CHART_INDICATOR_CATALOG],
        "marketContext": {
            "availableForEveryCanonicalSelection": True,
            "boundedDiagnosticsForDebugSelections": True,
            "canonicalSelectionCount": canonical_selection_count,
            "indicators": [
                "prior_structure",
                "comparable_volatility",
                "phase_adjusted_participation",
            ],
            "availability": "post_close_usable_next_bar",
            "phaseReferenceOccurrences": 20,
            "diagnosticOnly": True,
            "changesExecutionDecisions": False,
        },
        "onlineSignals": {
            "availableForEveryCanonicalSelection": True,
            "boundedReplayForDebugSelections": True,
            "persistentLiveSource": CANONICAL_SOURCE,
            "canonicalSelectionCount": canonical_selection_count,
            "algorithmVersion": "online_signal_v2",
            "availability": "post_close_usable_next_bar",
            "minimumClosedBarsForComposite": 193,
            "diagnosticOnly": True,
        },
        "minuteReplay": {
            "availableForEveryCanonicalSelection": True,
            "canonicalSelectionCount": canonical_selection_count,
            "sourceTimeframe": "1m",
            "maximumReplayDays": 730,
            "defaultReplayDays": 365,
            "syntheticFillPolicy": "excluded",
            "asWasLiveJournal": False,
            "profitabilityGuaranteed": False,
        },
        "forwardPaper": {
            "availableForEveryCanonicalSelection": True,
            "canonicalSelectionCount": canonical_selection_count,
            "statusEndpoint": "/api/paper/status",
            "sourceVintage": "append_only_first_seen",
            "cryptoFeedGrade": "live",
            "multiassetFallbackFeedGrade": "delayed",
            "realOrderRouting": False,
            "profitabilityGuaranteed": False,
        },
        "assets": assets,
    }
