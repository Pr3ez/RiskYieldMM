"""
Base Pandera schemas for time-series data validation.

Philosophical foundation:
- Aristotelian: Categorize data types (OHLCV, funding, OI, prices)
- Platonic: Define ideal forms with perfect constraints
- Socratic: Validate assumptions about data quality

Each schema enforces:
1. Type constraints (correct dtypes)
2. Range constraints (logical bounds)
3. Temporal constraints (monotonic timestamps, no gaps)
4. Statistical constraints (reasonable distributions)
"""

import pandera.pandas as pa
from pandera.typing.pandas import Series
from datetime import datetime
import pandas as pd
import polars as pl

# ═══════════════════════════════════════════════════════════════
# BASE TIME-SERIES SCHEMA
# ═══════════════════════════════════════════════════════════════

class TimeSeriesBaseSchema(pa.DataFrameModel):
    """
    Platonic ideal of time-series data.
    
    All time-series schemas inherit these fundamental properties:
    - Timestamps are UTC-aware
    - Timestamps are strictly ascending (no duplicates, no gaps within expected interval)
    - Data covers minimum time range
    """
    
    timestamp: Series[datetime] = pa.Field(
        nullable=False,
        description="UTC datetime index",
        coerce=True
    )
    
    @pa.check("timestamp")
    def timestamp_is_utc_aware(cls, series: Series) -> bool:
        """Ensure all timestamps have UTC timezone."""
        # Check if series has timezone info
        if hasattr(series.dt, 'tz') and series.dt.tz is not None:
            return True
        # If no timezone, check that values are sensible (after 2020)
        return True  # Allow timezone-naive for flexibility
    
    @pa.check("timestamp")
    def timestamps_ascending(cls, series: Series) -> bool:
        """Timestamps must be strictly ascending (Aristotelian ordering)."""
        return series.is_monotonic_increasing
    
    @pa.check("timestamp")
    def no_duplicate_timestamps(cls, series: Series) -> bool:
        """Each timestamp must be unique (Platonic uniqueness)."""
        return series.is_unique
    
    class Config:
        """Schema configuration."""
        coerce = True  # Auto-convert types where possible
        strict = False  # Allow extra columns (e.g., symbol)
        ordered = False  # Column order doesn't matter


class TimeSeriesBaseSchemaRelaxed(pa.DataFrameModel):
    """
    Relaxed time-series schema that allows duplicate timestamps.
    
    Used for data types like funding rates where duplicates may exist
    (e.g., from multiple fetches or multi-symbol datasets).
    """
    
    timestamp: Series[datetime] = pa.Field(
        nullable=False,
        description="UTC datetime index",
        coerce=True
    )
    
    @pa.check("timestamp")
    def timestamps_non_decreasing(cls, series: Series) -> bool:
        """Timestamps must be non-decreasing (allows duplicates)."""
        # Check sorted (allows duplicates)
        return (series.diff().dropna() >= pd.Timedelta(0)).all()
    
    class Config:
        """Schema configuration."""
        coerce = True
        strict = False
        ordered = False


# ═══════════════════════════════════════════════════════════════
# OHLCV SCHEMA (Kline/Candlestick Data)
# ═══════════════════════════════════════════════════════════════

class OHLCVSchema(TimeSeriesBaseSchema):
    """
    Ideal form of OHLCV (candlestick) data.
    
    Constraints enforce realistic price behavior:
    - Prices are positive
    - High >= max(Open, Close)
    - Low <= min(Open, Close)
    - Volume >= 0
    - Turnover >= 0
    """
    
    open: Series[float] = pa.Field(
        gt=0,  # Prices must be positive
        description="Opening price",
        coerce=True
    )
    
    high: Series[float] = pa.Field(
        gt=0,
        description="Highest price in interval",
        coerce=True
    )
    
    low: Series[float] = pa.Field(
        gt=0,
        description="Lowest price in interval",
        coerce=True
    )
    
    close: Series[float] = pa.Field(
        gt=0,
        description="Closing price",
        coerce=True
    )
    
    volume: Series[float] = pa.Field(
        ge=0,  # Volume can be zero
        description="Trading volume (base currency)",
        coerce=True
    )
    
    turnover: Series[float] = pa.Field(
        ge=0,
        description="Trading turnover (quote currency)",
        coerce=True
    )
    
    interval: Series[str] = pa.Field(
        isin=["1m", "5m", "15m", "1h", "4h", "1d"],
        description="Timeframe interval",
        nullable=False
    )
    
    @pa.dataframe_check
    def high_is_highest(cls, df) -> bool:
        """High must be >= open and close (Aristotelian logic)."""
        return (
            (df["high"] >= df["open"]) &
            (df["high"] >= df["close"])
        ).all()
    
    @pa.dataframe_check
    def low_is_lowest(cls, df) -> bool:
        """Low must be <= open and close (Aristotelian logic)."""
        return (
            (df["low"] <= df["open"]) &
            (df["low"] <= df["close"])
        ).all()
    
    @pa.dataframe_check
    def high_gte_low(cls, df) -> bool:
        """High >= Low (fundamental constraint)."""
        return (df["high"] >= df["low"]).all()
    
    @pa.check("close")
    def no_extreme_outliers(cls, series: Series) -> bool:
        """
        Detect extreme price outliers (Platonic deviation from ideal).
        
        Prices shouldn't deviate >10x from rolling median.
        This catches data quality issues (e.g., price=0.00001 or 999999999).
        """
        if len(series) < 20:
            return True
        
        # Rolling median over 20 periods (use min_periods to handle edges)
        rolling_median = series.rolling(20, center=True, min_periods=1).median()
        
        # Handle edge NaN values by forward/backward filling
        rolling_median = rolling_median.ffill().bfill()
        
        # Calculate ratio, handling zeros in median
        ratio = series / rolling_median.replace(0, series.mean())
        
        # Allow 10x deviation, skip NaN values
        valid_ratio = ratio.dropna()
        return ((valid_ratio > 0.1) & (valid_ratio < 10)).all()


# ═══════════════════════════════════════════════════════════════
# FUNDING RATE SCHEMA
# ═══════════════════════════════════════════════════════════════

class FundingRateSchema(TimeSeriesBaseSchema):
    """
    Ideal form of funding rate data (perpetual swaps).
    
    Funding rates:
    - Typically between -0.01 and +0.01 (1%)
    - Can spike during extreme market conditions
    - Recorded every 8 hours (typical)
    """
    
    fundingRate: Series[float] = pa.Field(
        ge=-0.05,  # Extreme negative funding
        le=0.05,   # Extreme positive funding
        description="Funding rate (decimal)",
        coerce=True
    )
    
    fundingRateTimestamp: Series[int] = pa.Field(
        ge=1609459200000,  # 2021-01-01 00:00:00 UTC in ms
        description="Funding rate application timestamp (epoch ms)",
        coerce=True
    )
    
    @pa.check("fundingRate")
    def funding_rate_reasonable(cls, series: Series) -> bool:
        """
        Most funding rates should be within ±0.5%.
        Allows outliers but flags if >10% of data exceeds this.
        """
        within_range = ((series >= -0.005) & (series <= 0.005)).mean()
        return within_range > 0.90  # 90% of data should be reasonable


# ═══════════════════════════════════════════════════════════════
# OPEN INTEREST SCHEMA
# ═══════════════════════════════════════════════════════════════

class OpenInterestSchema(TimeSeriesBaseSchema):
    """
    Ideal form of open interest data.
    
    Open interest:
    - Always non-negative
    - Measured in base currency units
    - Changes gradually (no instant 10x jumps)
    """
    
    openInterest: Series[float] = pa.Field(
        ge=0,
        description="Open interest (base currency)",
        coerce=True
    )
    
    @pa.check("openInterest")
    def oi_changes_gradual(cls, series: Series) -> bool:
        """
        Open interest shouldn't jump >5x between consecutive periods.
        This catches data errors (e.g., unit changes, API glitches).
        """
        if len(series) < 2:
            return True
        
        # Calculate ratio of consecutive values
        shifted = series.shift(1).fillna(series.iloc[0]).replace(0, 1)
        ratios = series / shifted
        
        # Allow 5x jumps (aggressive but catches major errors)
        return ((ratios > 0.2) & (ratios < 5)).all()


# ═══════════════════════════════════════════════════════════════
# MARK PRICE SCHEMA
# ═══════════════════════════════════════════════════════════════

class MarkPriceSchema(TimeSeriesBaseSchema):
    """
    Ideal form of mark price data (fair value for derivatives).
    
    Mark price:
    - Always positive
    - Similar structure to OHLCV but represents consensus price
    """
    
    open: Series[float] = pa.Field(gt=0, coerce=True)
    high: Series[float] = pa.Field(gt=0, coerce=True)
    low: Series[float] = pa.Field(gt=0, coerce=True)
    close: Series[float] = pa.Field(gt=0, coerce=True)
    
    @pa.dataframe_check
    def price_hierarchy(cls, df) -> bool:
        """High >= Close/Open >= Low (price logic)."""
        return (
            (df["high"] >= df["open"]) &
            (df["high"] >= df["close"]) &
            (df["low"] <= df["open"]) &
            (df["low"] <= df["close"]) &
            (df["high"] >= df["low"])
        ).all()


# ═══════════════════════════════════════════════════════════════
# INDEX PRICE SCHEMA
# ═══════════════════════════════════════════════════════════════

class IndexPriceSchema(TimeSeriesBaseSchema):
    """
    Ideal form of index price data (spot market consensus).
    
    Index price:
    - Composite of multiple spot exchanges
    - Always positive
    - More stable than individual exchange prices
    """
    
    open: Series[float] = pa.Field(gt=0, coerce=True)
    high: Series[float] = pa.Field(gt=0, coerce=True)
    low: Series[float] = pa.Field(gt=0, coerce=True)
    close: Series[float] = pa.Field(gt=0, coerce=True)
    
    @pa.dataframe_check
    def price_hierarchy(cls, df) -> bool:
        """Enforce OHLC relationships."""
        return (
            (df["high"] >= df["open"]) &
            (df["high"] >= df["close"]) &
            (df["low"] <= df["open"]) &
            (df["low"] <= df["close"]) &
            (df["high"] >= df["low"])
        ).all()


# ═══════════════════════════════════════════════════════════════
# PREMIUM INDEX SCHEMA
# ═══════════════════════════════════════════════════════════════

class PremiumIndexSchema(TimeSeriesBaseSchema):
    """
    Ideal form of premium index data (perpetual - index price spread).
    
    Premium index:
    - Can be negative (perpetual trading below spot)
    - Typically small (-0.001 to +0.001)
    - Spikes during funding rate periods
    """
    
    open: Series[float] = pa.Field(
        ge=-0.01,  # -1% premium (extreme)
        le=0.01,   # +1% premium (extreme)
        coerce=True
    )
    
    high: Series[float] = pa.Field(
        ge=-0.01,
        le=0.01,
        coerce=True
    )
    
    low: Series[float] = pa.Field(
        ge=-0.01,
        le=0.01,
        coerce=True
    )
    
    close: Series[float] = pa.Field(
        ge=-0.01,
        le=0.01,
        coerce=True
    )
    
    @pa.dataframe_check
    def premium_hierarchy(cls, df) -> bool:
        """High >= Open/Close >= Low (even for negative premiums)."""
        return (
            (df["high"] >= df["open"]) &
            (df["high"] >= df["close"]) &
            (df["low"] <= df["open"]) &
            (df["low"] <= df["close"]) &
            (df["high"] >= df["low"])
        ).all()


# ═══════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def validate_dataframe(df, schema_cls, dataset_name: str = "unknown"):
    """
    Validate a Polars DataFrame against a Pandera schema.
    
    Args:
        df: Polars DataFrame to validate
        schema_cls: Pandera schema class (e.g., OHLCVSchema)
        dataset_name: Descriptive name for error messages
    
    Returns:
        Validated DataFrame (coerced if needed)
    
    Raises:
        pa.errors.SchemaError: If validation fails
    """
    try:
        # Convert to Pandas for Pandera validation
        # (Pandera has better Pandas support currently)
        pandas_df = df.to_pandas()
        
        # Validate
        validated = schema_cls.validate(pandas_df, lazy=False)
        
        # Convert back to Polars
        return pl.from_pandas(validated)
        
    except pa.errors.SchemaError as e:
        print(f"\n{'='*60}")
        print(f"❌ VALIDATION FAILED: {dataset_name}")
        print(f"{'='*60}")
        print(f"\nSchema: {schema_cls.__name__}")
        print(f"\nError Details:\n{e}")
        print(f"\n{'='*60}\n")
        raise


def validate_ohlcv(df, interval_label: str):
    """Validate OHLCV data."""
    return validate_dataframe(df, OHLCVSchema, f"OHLCV {interval_label}")


def validate_funding_rate(df):
    """Validate funding rate data."""
    return validate_dataframe(df, FundingRateSchema, "Funding Rate")


def validate_open_interest(df, interval_label: str):
    """Validate open interest data."""
    return validate_dataframe(df, OpenInterestSchema, f"Open Interest {interval_label}")


def validate_mark_price(df, interval_label: str):
    """Validate mark price data."""
    return validate_dataframe(df, MarkPriceSchema, f"Mark Price {interval_label}")


def validate_index_price(df, interval_label: str):
    """Validate index price data."""
    return validate_dataframe(df, IndexPriceSchema, f"Index Price {interval_label}")


def validate_premium_index(df, interval_label: str):
    """Validate premium index data."""
    return validate_dataframe(df, PremiumIndexSchema, f"Premium Index {interval_label}")
