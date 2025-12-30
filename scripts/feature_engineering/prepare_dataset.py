"""
Dataset Preparation Script for RiskYieldMM
==========================================
Merges all 8h Bybit data sources into a single dataset with proper RAW_ prefixed columns.

Data Sources (all 8h timeframe):
- OHLCV (sorted-8h-bybit-linear) → RAW_P_*, RAW_L_*, RAW_TM_*
- Mark Price (mark-price-8h-bybit-linear) → RAW_P_mark*
- Index Price (index-price-8h-bybit-linear) → RAW_P_index*
- Premium (premium-price-8h-bybit-linear) → RAW_D_F_S_premium*
- Open Interest (open-interest-8h-bybit-linear) → RAW_L_S_openInterest
- Funding Rate (funding-rate-bybit-linear) → RAW_F_I_S_fundingRate
- Long/Short Ratio (long-short-ratio-8h-bybit-linear) → RAW_S_*

Output:
- Merged parquet with all RAW_ columns
- Ready for feature engineering

Usage:
    python prepare_dataset.py                     # Merge only
    python prepare_dataset.py --compute-features  # Merge + compute all features
    python prepare_dataset.py --output data.parquet  # Custom output path

Author: RiskYieldMM Project
Created: 2025-12-22
"""

import argparse
from pathlib import Path

import pandas as pd

# =============================================================================
# COLUMN MAPPINGS (Per Part 2 Raw Docs)
# =============================================================================

# File column → RAW_ feature name mapping

OHLCV_COLUMNS = {
    "timestamp": "RAW_TM_timestamp",
    "open": "RAW_P_open_abs_NN",
    "high": "RAW_P_high_abs_NN",
    "low": "RAW_P_low_abs_NN",
    "close": "RAW_P_close_abs_NN",
    "volume": "RAW_L_volume_abs_NN",
    "turnover": "RAW_L_turnover_abs_NN",
}

MARK_PRICE_COLUMNS = {
    "open": "RAW_P_markOpen_abs_NN",
    "high": "RAW_P_markHigh_abs_NN",
    "low": "RAW_P_markLow_abs_NN",
    "close": "RAW_P_markClose_abs_NN",
}

INDEX_PRICE_COLUMNS = {
    "open": "RAW_P_indexOpen_abs_NN",
    "high": "RAW_P_indexHigh_abs_NN",
    "low": "RAW_P_indexLow_abs_NN",
    "close": "RAW_P_indexClose_abs_NN",
}

PREMIUM_COLUMNS = {
    "open": "RAW_D_F_S_premiumOpen_pct_N",
    "high": "RAW_D_F_S_premiumHigh_pct_N",
    "low": "RAW_D_F_S_premiumLow_pct_N",
    "close": "RAW_D_F_S_premiumClose_pct_N",
}

OI_COLUMNS = {
    "openInterest": "RAW_L_S_openInterest_abs_NN",
}

FUNDING_COLUMNS = {
    "fundingRate": "RAW_F_I_S_fundingRate_pct_N",
}

LS_RATIO_COLUMNS = {
    "buyRatio": "RAW_S_buyRatio_bnd_N",
    "sellRatio": "RAW_S_sellRatio_bnd_N",
    # Derived: longShortRatio = buyRatio / sellRatio
}


# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================


def load_ohlcv(data_dir: Path) -> pd.DataFrame:
    """Load OHLCV data with proper RAW_ column names."""
    df = pd.read_parquet(data_dir / "sorted-8h-bybit-linear/btcusdt_8h.parquet")
    df = df.rename(columns=OHLCV_COLUMNS)
    # Drop interval column (metadata, not needed)
    if "interval" in df.columns:
        df = df.drop(columns=["interval"])
    return df


def load_mark_price(data_dir: Path) -> pd.DataFrame:
    """Load mark price data with proper RAW_ column names."""
    df = pd.read_parquet(
        data_dir / "mark-price-8h-bybit-linear/btcusdt_mark_price_8h.parquet"
    )
    df = df.rename(columns=MARK_PRICE_COLUMNS)
    return df


def load_index_price(data_dir: Path) -> pd.DataFrame:
    """Load index price data with proper RAW_ column names."""
    df = pd.read_parquet(
        data_dir / "index-price-8h-bybit-linear/btcusdt_index_price_8h.parquet"
    )
    df = df.rename(columns=INDEX_PRICE_COLUMNS)
    return df


def load_premium(data_dir: Path) -> pd.DataFrame:
    """Load premium index data with proper RAW_ column names."""
    df = pd.read_parquet(
        data_dir / "premium-price-8h-bybit-linear/btcusdt_premium_price_8h.parquet"
    )
    df = df.rename(columns=PREMIUM_COLUMNS)
    return df


def load_open_interest(data_dir: Path) -> pd.DataFrame:
    """Load open interest data with proper RAW_ column names."""
    df = pd.read_parquet(
        data_dir / "open-interest-8h-bybit-linear/btcusdt_open_interest_8h.parquet"
    )
    df = df.rename(columns=OI_COLUMNS)
    return df


def load_funding_rate(data_dir: Path) -> pd.DataFrame:
    """Load funding rate data with proper RAW_ column names."""
    df = pd.read_parquet(
        data_dir / "funding-rate-bybit-linear/btcusdt_funding_rate.parquet"
    )
    df = df.rename(columns=FUNDING_COLUMNS)
    # Drop redundant columns
    df = df.drop(columns=["symbol", "fundingRateTimestamp"], errors="ignore")
    return df


def load_long_short_ratio(data_dir: Path) -> pd.DataFrame:
    """Load long/short ratio data with proper RAW_ column names."""
    df = pd.read_parquet(
        data_dir / "long-short-ratio-8h-bybit-linear/btcusdt_ls_ratio.parquet"
    )
    df = df.rename(columns=LS_RATIO_COLUMNS)
    # Compute derived ratio
    df["RAW_S_longShortRatio_rat_N"] = (
        df["RAW_S_buyRatio_bnd_N"] / df["RAW_S_sellRatio_bnd_N"]
    )
    # Drop redundant columns
    df = df.drop(columns=["timestamp_ms"], errors="ignore")
    return df


# =============================================================================
# MERGE FUNCTION
# =============================================================================


def merge_all_sources(data_dir: Path) -> pd.DataFrame:
    """
    Merge all 8h data sources into a single DataFrame.

    Merge strategy:
    - OHLCV is the base (all other sources merge onto it)
    - Left join preserves all OHLCV rows
    - Some sources (L/S ratio) start later → NaN for early rows

    Returns:
        DataFrame with all RAW_ columns, sorted by timestamp
    """
    print("Loading data sources...")

    # Load all sources
    ohlcv = load_ohlcv(data_dir)
    print(f"  OHLCV: {len(ohlcv):,} rows")

    mark = load_mark_price(data_dir)
    print(f"  Mark Price: {len(mark):,} rows")

    index = load_index_price(data_dir)
    print(f"  Index Price: {len(index):,} rows")

    premium = load_premium(data_dir)
    print(f"  Premium: {len(premium):,} rows")

    oi = load_open_interest(data_dir)
    print(f"  Open Interest: {len(oi):,} rows")

    funding = load_funding_rate(data_dir)
    print(f"  Funding Rate: {len(funding):,} rows")

    ls_ratio = load_long_short_ratio(data_dir)
    print(f"  Long/Short Ratio: {len(ls_ratio):,} rows")

    # Merge all onto OHLCV base
    print("\nMerging data sources...")

    df = ohlcv.copy()

    # Mark price (all OHLC) - join on timestamp
    mark_cols = [c for c in mark.columns if c.startswith("RAW_")]
    df = df.merge(
        mark[["timestamp"] + mark_cols],
        left_on="RAW_TM_timestamp",
        right_on="timestamp",
        how="left",
    ).drop(columns=["timestamp"])

    # Index price (all OHLC)
    index_cols = [c for c in index.columns if c.startswith("RAW_")]
    df = df.merge(
        index[["timestamp"] + index_cols],
        left_on="RAW_TM_timestamp",
        right_on="timestamp",
        how="left",
    ).drop(columns=["timestamp"])

    # Premium (all OHLC)
    premium_cols = [c for c in premium.columns if c.startswith("RAW_")]
    df = df.merge(
        premium[["timestamp"] + premium_cols],
        left_on="RAW_TM_timestamp",
        right_on="timestamp",
        how="left",
    ).drop(columns=["timestamp"])

    # Open Interest
    oi_cols = [c for c in oi.columns if c.startswith("RAW_")]
    df = df.merge(
        oi[["timestamp"] + oi_cols],
        left_on="RAW_TM_timestamp",
        right_on="timestamp",
        how="left",
    ).drop(columns=["timestamp"])

    # Funding Rate
    funding_cols = [c for c in funding.columns if c.startswith("RAW_")]
    df = df.merge(
        funding[["timestamp"] + funding_cols],
        left_on="RAW_TM_timestamp",
        right_on="timestamp",
        how="left",
    ).drop(columns=["timestamp"])

    # Long/Short Ratio (starts later in time)
    ls_cols = [c for c in ls_ratio.columns if c.startswith("RAW_")]
    df = df.merge(
        ls_ratio[["timestamp"] + ls_cols],
        left_on="RAW_TM_timestamp",
        right_on="timestamp",
        how="left",
    ).drop(columns=["timestamp"])

    # Sort by timestamp
    df = df.sort_values("RAW_TM_timestamp").reset_index(drop=True)

    return df


# =============================================================================
# SUMMARY FUNCTIONS
# =============================================================================


def print_dataset_summary(df: pd.DataFrame) -> None:
    """Print summary of merged dataset."""
    print("\n" + "=" * 70)
    print("MERGED DATASET SUMMARY")
    print("=" * 70)

    print(f"\nTotal rows: {len(df):,}")
    print(
        f"Date range: {df['RAW_TM_timestamp'].min()} to {df['RAW_TM_timestamp'].max()}"
    )

    # Group columns by category
    raw_cols = [c for c in df.columns if c.startswith("RAW_")]

    categories = {
        "Price (P)": [c for c in raw_cols if "_P_" in c],
        "Liquidity (L)": [c for c in raw_cols if "_L_" in c and "_S_" not in c],
        "Liquidity+Sentiment (L_S)": [c for c in raw_cols if "_L_S_" in c],
        "Funding (F)": [c for c in raw_cols if "_F_" in c and "_D_" not in c],
        "Derivative/Premium (D)": [c for c in raw_cols if "_D_" in c],
        "Sentiment (S)": [
            c
            for c in raw_cols
            if "_S_" in c and "_D_" not in c and "_L_" not in c and "_F_" not in c
        ],
        "Temporal (TM)": [c for c in raw_cols if "_TM_" in c],
    }

    print(f"\nTotal RAW columns: {len(raw_cols)}")
    for cat_name, cols in categories.items():
        if cols:
            print(f"  {cat_name}: {len(cols)}")

    # Check for NaN
    print("\nNaN counts (top 10):")
    nan_counts = df[raw_cols].isna().sum().sort_values(ascending=False)
    for col, count in nan_counts.head(10).items():
        if count > 0:
            print(f"  {col}: {count:,} ({100 * count / len(df):.1f}%)")

    print("\nColumn list:")
    for col in sorted(raw_cols):
        print(f"  {col}")


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Merge 8h Bybit data sources into a single dataset"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="fetchingByBit",
        help="Path to data directory (default: fetchingByBit)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/merged_8h_raw.parquet",
        help="Output parquet file path (default: data/merged_8h_raw.parquet)",
    )
    parser.add_argument(
        "--compute-features",
        action="store_true",
        help="Also compute all engineered features",
    )
    parser.add_argument(
        "--features-output",
        type=str,
        default="data/features_8h.parquet",
        help="Output path for features (default: data/features_8h.parquet)",
    )
    args = parser.parse_args()

    # Resolve paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    data_dir = project_root / args.data_dir

    print("=" * 70)
    print("RiskYieldMM Dataset Preparation")
    print("=" * 70)
    print(f"Data directory: {data_dir}")

    # Merge all sources
    df = merge_all_sources(data_dir)

    # Print summary
    print_dataset_summary(df)

    # Export merged raw data
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = project_root / output_path

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(output_path)
    print(f"\n✓ Saved merged raw data to: {output_path}")

    # Optionally compute features
    if args.compute_features:
        print("\n" + "=" * 70)
        print("COMPUTING FEATURES")
        print("=" * 70)

        # Import compute_all_features from the main module
        from compute_features import compute_all_features

        # Prepare df for compute_all_features (it expects non-RAW column names)
        df_for_compute = df.copy()

        # Map RAW_ columns back to simple names expected by compute_features
        rename_map = {
            "RAW_TM_timestamp": "timestamp",
            "RAW_P_open_abs_NN": "open",
            "RAW_P_high_abs_NN": "high",
            "RAW_P_low_abs_NN": "low",
            "RAW_P_close_abs_NN": "close",
            "RAW_L_volume_abs_NN": "volume",
            "RAW_L_turnover_abs_NN": "turnover",
            "RAW_P_markOpen_abs_NN": "markOpen",
            "RAW_P_markHigh_abs_NN": "markHigh",
            "RAW_P_markLow_abs_NN": "markLow",
            "RAW_P_markClose_abs_NN": "markClose",
            "RAW_P_indexOpen_abs_NN": "indexOpen",
            "RAW_P_indexHigh_abs_NN": "indexHigh",
            "RAW_P_indexLow_abs_NN": "indexLow",
            "RAW_P_indexClose_abs_NN": "indexClose",
            "RAW_D_F_S_premiumOpen_pct_N": "premiumOpen",
            "RAW_D_F_S_premiumHigh_pct_N": "premiumHigh",
            "RAW_D_F_S_premiumLow_pct_N": "premiumLow",
            "RAW_D_F_S_premiumClose_pct_N": "premiumClose",
            "RAW_L_S_openInterest_abs_NN": "openInterest",
            "RAW_F_I_S_fundingRate_pct_N": "fundingRate",
            "RAW_S_buyRatio_bnd_N": "buyRatio",
            "RAW_S_sellRatio_bnd_N": "sellRatio",
            "RAW_S_longShortRatio_rat_N": "longShortRatio",
        }

        df_for_compute = df_for_compute.rename(columns=rename_map)

        # Compute features
        features = compute_all_features(df_for_compute)

        feature_cols = [c for c in features.columns if c != "timestamp"]
        print(f"Computed {len(feature_cols)} features")

        # Export features
        features_path = Path(args.features_output)
        if not features_path.is_absolute():
            features_path = project_root / features_path

        features_path.parent.mkdir(parents=True, exist_ok=True)
        features.to_parquet(features_path)
        print(f"✓ Saved features to: {features_path}")

    print("\n" + "=" * 70)
    print("Done!")
    print("=" * 70)


if __name__ == "__main__":
    main()
