"""
Usage examples and testing for Pandera schemas.

This module demonstrates how to use the validation schemas
and provides test cases for schema correctness.

Run from project root:
    python -m schemas.examples
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import polars as pl
from datetime import datetime, timezone, timedelta
from schemas.base_schemas import (
    validate_ohlcv,
    validate_funding_rate,
    validate_open_interest,
    OHLCVSchema,
    FundingRateSchema
)


def create_sample_ohlcv() -> pl.DataFrame:
    """Create sample OHLCV data that passes validation."""
    dates = [datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i) for i in range(100)]
    
    return pl.DataFrame({
        "timestamp": dates,
        "open": [100.0 + i * 0.1 for i in range(100)],
        "high": [100.5 + i * 0.1 for i in range(100)],
        "low": [99.5 + i * 0.1 for i in range(100)],
        "close": [100.2 + i * 0.1 for i in range(100)],
        "volume": [1000.0 + i * 10 for i in range(100)],
        "turnover": [100000.0 + i * 1000 for i in range(100)],
        "interval": ["1m"] * 100
    })


def create_invalid_ohlcv() -> pl.DataFrame:
    """Create OHLCV data that FAILS validation (for testing)."""
    dates = [datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i) for i in range(10)]
    
    return pl.DataFrame({
        "timestamp": dates,
        "open": [100.0] * 10,
        "high": [99.0] * 10,  # ❌ High < Open (violates constraint)
        "low": [101.0] * 10,   # ❌ Low > Open (violates constraint)
        "close": [100.0] * 10,
        "volume": [1000.0] * 10,
        "turnover": [100000.0] * 10,
        "interval": ["1m"] * 10
    })


def test_valid_data():
    """Test that valid data passes validation."""
    print("Testing valid OHLCV data...")
    df = create_sample_ohlcv()
    validated_df = validate_ohlcv(df, "1m")
    print(f"✅ Validation passed: {validated_df.height} rows")
    return validated_df


def test_invalid_data():
    """Test that invalid data fails validation."""
    print("\nTesting invalid OHLCV data (should fail)...")
    df = create_invalid_ohlcv()
    try:
        validate_ohlcv(df, "1m")
        print("❌ Validation should have failed but didn't!")
    except Exception as e:
        print(f"✅ Validation correctly failed: {type(e).__name__}")


def example_usage():
    """Demonstrate typical usage pattern."""
    print("\n" + "="*60)
    print("PANDERA SCHEMA VALIDATION - USAGE EXAMPLE")
    print("="*60)
    
    # Load data (in real use, this would be from parquet)
    print("\n1. Creating sample data...")
    df = create_sample_ohlcv()
    print(f"   Loaded {df.height} rows")
    
    # Validate before processing
    print("\n2. Validating against OHLCVSchema...")
    try:
        validated_df = validate_ohlcv(df, "1m")
        print(f"   ✅ Validation passed")
        print(f"   Data shape: {validated_df.shape}")
        print(f"   Timestamp range: {validated_df['timestamp'].min()} to {validated_df['timestamp'].max()}")
    except Exception as e:
        print(f"   ❌ Validation failed: {e}")
        return None
    
    # Use validated data
    print("\n3. Using validated data for ML pipeline...")
    print("   [Data is now guaranteed to be clean and correct]")
    
    return validated_df


if __name__ == "__main__":
    # Run examples
    test_valid_data()
    test_invalid_data()
    example_usage()
