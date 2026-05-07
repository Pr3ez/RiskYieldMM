"""Configured non-crypto assets for the multi-asset source layer.

The parquet output intentionally stays close to the current Bybit OHLCV
contract. Metadata belongs here and in sidecar manifests, not in the model-facing
bar files.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PROVIDER = "twelvedata"
DEFAULT_MARKET = "multi"
DATABENTO_PROVIDER = "databento"
DATABENTO_MARKET = "futures"
YFINANCE_PROVIDER = "yfinance"
YFINANCE_MARKET = "futures"
DATABENTO_DATASET = "GLBX.MDP3"
DATABENTO_SCHEMA = "ohlcv-1m"
DATABENTO_STYPE_IN = "continuous"
DEFAULT_START_DATE = "2021-01-01"
DEFAULT_END_DATE = "now"
DEFAULT_INTERVALS = ("1m", "5m", "15m", "1h", "4h", "1d")
HTF_REQUIRED_INTERVALS = ("1m", "15m")

TWELVE_DATA_INTERVALS = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1day",
}

INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


@dataclass(frozen=True)
class AssetSpec:
    """One canonical asset and provider symbol mapping."""

    symbol: str
    display_name: str
    provider_symbol: str
    asset_class: str
    market_type: str
    volume_type: str
    notes: str = ""

    @property
    def slug(self) -> str:
        return self.symbol.lower()


@dataclass(frozen=True)
class DatabentoFuturesSpec:
    """Databento futures proxy mapped to a canonical dataset id."""

    symbol: str
    display_name: str
    provider_symbol: str
    dataset: str = DATABENTO_DATASET
    schema: str = DATABENTO_SCHEMA
    stype_in: str = DATABENTO_STYPE_IN
    asset_class: str = "futures"
    market_type: str = "continuous_future"
    volume_type: str = "real"
    price_transform: str = "identity"
    notes: str = ""

    @property
    def slug(self) -> str:
        return self.symbol.lower()


@dataclass(frozen=True)
class YFinanceFuturesSpec:
    """Yahoo Finance futures symbol used only as a recent-tail fallback."""

    symbol: str
    display_name: str
    provider_symbol: str
    asset_class: str = "futures"
    market_type: str = "front_future"
    volume_type: str = "indicative"
    price_transform: str = "identity"
    notes: str = ""

    @property
    def slug(self) -> str:
        return self.symbol.lower()


ASSETS = (
    AssetSpec(
        symbol="EURUSD",
        display_name="EUR/USD",
        provider_symbol="EUR/USD",
        asset_class="fx",
        market_type="spot",
        volume_type="none",
        notes="Spot FX pair.",
    ),
    AssetSpec(
        symbol="USDJPY",
        display_name="USD/JPY",
        provider_symbol="USD/JPY",
        asset_class="fx",
        market_type="spot",
        volume_type="none",
        notes="Spot FX pair.",
    ),
    AssetSpec(
        symbol="XAUUSD",
        display_name="Gold spot",
        provider_symbol="XAU/USD",
        asset_class="metal",
        market_type="spot",
        volume_type="none",
        notes="Gold spot quoted against USD. Provider symbol must be verified by symbol discovery.",
    ),
    AssetSpec(
        symbol="WTIUSD",
        display_name="WTI crude oil",
        provider_symbol="WTI/USD",
        asset_class="commodity",
        market_type="spot_or_cfd",
        volume_type="indicative",
        notes="Oil symbol is provider-dependent; verify before production backfill.",
    ),
    AssetSpec(
        symbol="SPX",
        display_name="S&P 500 index",
        provider_symbol="SPX",
        asset_class="index",
        market_type="cash_index",
        volume_type="none",
        notes="Cash index target. Futures-quality alternative is ES via Databento later.",
    ),
    AssetSpec(
        symbol="NDX",
        display_name="Nasdaq 100 index",
        provider_symbol="NDX",
        asset_class="index",
        market_type="cash_index",
        volume_type="none",
        notes="Assumes Nasdaq means Nasdaq 100. Use IXIC if Nasdaq Composite is required.",
    ),
)


DATABENTO_FUTURES = (
    DatabentoFuturesSpec(
        symbol="EURUSD",
        display_name="EUR/USD futures proxy",
        provider_symbol="6E.v.0",
        asset_class="fx",
        notes="CME Euro FX volume-based front continuous contract; quoted USD per EUR.",
    ),
    DatabentoFuturesSpec(
        symbol="USDJPY",
        display_name="USD/JPY futures proxy",
        provider_symbol="6J.v.0",
        asset_class="fx",
        price_transform="inverse",
        notes=(
            "CME Japanese Yen futures are quoted USD per JPY; prices are "
            "inverted to store a USD/JPY-like OHLC path."
        ),
    ),
    DatabentoFuturesSpec(
        symbol="GC",
        display_name="Gold futures",
        provider_symbol="GC.v.0",
        notes="COMEX gold volume-based front continuous contract, unadjusted prices.",
    ),
    DatabentoFuturesSpec(
        symbol="CL",
        display_name="WTI crude oil futures",
        provider_symbol="CL.v.0",
        notes="NYMEX WTI crude volume-based front continuous contract, unadjusted prices.",
    ),
    DatabentoFuturesSpec(
        symbol="ES",
        display_name="E-mini S&P 500 futures",
        provider_symbol="ES.v.0",
        notes="CME E-mini S&P 500 volume-based front continuous contract, unadjusted prices.",
    ),
    DatabentoFuturesSpec(
        symbol="NQ",
        display_name="E-mini Nasdaq 100 futures",
        provider_symbol="NQ.v.0",
        notes="CME E-mini Nasdaq 100 volume-based front continuous contract, unadjusted prices.",
    ),
)


YFINANCE_FUTURES = (
    YFinanceFuturesSpec(
        symbol="EURUSD",
        display_name="Euro FX futures recent-tail proxy",
        provider_symbol="6E=F",
        asset_class="fx",
        notes="Yahoo Euro FX futures. Use only after overlap validation against Databento 6E.v.0.",
    ),
    YFinanceFuturesSpec(
        symbol="USDJPY",
        display_name="Japanese Yen futures recent-tail proxy",
        provider_symbol="6J=F",
        asset_class="fx",
        price_transform="inverse",
        notes=(
            "Yahoo Japanese Yen futures. Prices are inverted to match the "
            "Databento USDJPY-like OHLC path."
        ),
    ),
    YFinanceFuturesSpec(
        symbol="GC",
        display_name="Gold futures recent-tail proxy",
        provider_symbol="GC=F",
        notes="Yahoo gold futures. Use only after overlap validation against Databento GC.v.0.",
    ),
    YFinanceFuturesSpec(
        symbol="CL",
        display_name="WTI crude oil futures recent-tail proxy",
        provider_symbol="CL=F",
        notes="Yahoo crude oil futures. Use only after overlap validation against Databento CL.v.0.",
    ),
    YFinanceFuturesSpec(
        symbol="ES",
        display_name="E-mini S&P 500 futures recent-tail proxy",
        provider_symbol="ES=F",
        notes="Yahoo E-mini S&P 500 futures. Use only after overlap validation against Databento ES.v.0.",
    ),
    YFinanceFuturesSpec(
        symbol="NQ",
        display_name="E-mini Nasdaq 100 futures recent-tail proxy",
        provider_symbol="NQ=F",
        notes="Yahoo E-mini Nasdaq 100 futures. Use only after overlap validation against Databento NQ.v.0.",
    ),
)


def normalized_asset_ids(
    asset_ids: tuple[str, ...] | list[str] | None = None,
) -> tuple[str, ...]:
    """Return uppercase canonical ids with stable order and duplicates removed."""
    raw_ids = (
        asset_ids if asset_ids is not None else tuple(asset.symbol for asset in ASSETS)
    )
    seen: set[str] = set()
    normalized: list[str] = []
    for asset_id in raw_ids:
        cleaned = str(asset_id).strip().upper()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            normalized.append(cleaned)
    return tuple(normalized)


def assets_by_symbol() -> dict[str, AssetSpec]:
    return {asset.symbol: asset for asset in ASSETS}


def selected_assets(
    asset_ids: tuple[str, ...] | list[str] | None = None,
) -> tuple[AssetSpec, ...]:
    """Resolve configured assets by canonical id."""
    by_symbol = assets_by_symbol()
    selected = []
    for asset_id in normalized_asset_ids(asset_ids):
        if asset_id not in by_symbol:
            known = ", ".join(sorted(by_symbol))
            raise KeyError(f"Unknown asset {asset_id!r}. Known assets: {known}")
        selected.append(by_symbol[asset_id])
    return tuple(selected)


def databento_futures_by_symbol() -> dict[str, DatabentoFuturesSpec]:
    return {asset.symbol: asset for asset in DATABENTO_FUTURES}


def selected_databento_futures(
    asset_ids: tuple[str, ...] | list[str] | None = None,
) -> tuple[DatabentoFuturesSpec, ...]:
    """Resolve configured Databento futures by canonical id."""
    by_symbol = databento_futures_by_symbol()
    raw_ids = (
        asset_ids
        if asset_ids is not None
        else tuple(asset.symbol for asset in DATABENTO_FUTURES)
    )
    selected = []
    for asset_id in normalized_asset_ids(raw_ids):
        if asset_id not in by_symbol:
            known = ", ".join(sorted(by_symbol))
            raise KeyError(
                f"Unknown Databento futures asset {asset_id!r}. Known: {known}"
            )
        selected.append(by_symbol[asset_id])
    return tuple(selected)


def yfinance_futures_by_symbol() -> dict[str, YFinanceFuturesSpec]:
    return {asset.symbol: asset for asset in YFINANCE_FUTURES}


def selected_yfinance_futures(
    asset_ids: tuple[str, ...] | list[str] | None = None,
) -> tuple[YFinanceFuturesSpec, ...]:
    """Resolve configured Yahoo Finance futures by canonical id."""
    by_symbol = yfinance_futures_by_symbol()
    raw_ids = (
        asset_ids
        if asset_ids is not None
        else tuple(asset.symbol for asset in YFINANCE_FUTURES)
    )
    selected = []
    for asset_id in normalized_asset_ids(raw_ids):
        if asset_id not in by_symbol:
            known = ", ".join(sorted(by_symbol))
            raise KeyError(
                f"Unknown Yahoo Finance futures asset {asset_id!r}. Known: {known}"
            )
        selected.append(by_symbol[asset_id])
    return tuple(selected)
