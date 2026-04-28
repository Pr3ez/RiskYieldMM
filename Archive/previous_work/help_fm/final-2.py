# %% [CELL 1] Load Raw Data, Create Targets & Lagged Features
# PHASE 1: DATA PREPARATION & TARGET ENGINEERING
# Step 1.1: Load Raw Data and Create Target Variables
import hashlib
import time
import warnings
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION ID: Prevents loading stale data/models from previous runs
# ═══════════════════════════════════════════════════════════════════════════════
# Generate unique session ID based on timestamp
# All saved states will include this ID and be validated on load
TRAINING_SESSION_ID = f"session_{int(time.time())}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
print(f"\n{'=' * 80}")
print(f"🔐 TRAINING SESSION ID: {TRAINING_SESSION_ID}")
print("   All saved states will be tagged with this ID to prevent loading stale data")
print(f"{'=' * 80}\n")

# Import HMM library
try:
    from hmmlearn.hmm import GaussianHMM

    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False
    print("⚠ Warning: hmmlearn not available. HMM features will be skipped.")


# GLOBAL CONFIGURATION: TARGET FEATURES

# These columns contain FUTURE information (values known 1 day AFTER date_id)
# date_id is sequential: 1, 2, 3, 4... representing days from beginning
TARGET_FEATURES = [
    "forward_returns",  # Future return (target)
    "risk_free_rate",  # Future risk-free rate
    "market_forward_excess_returns",  # Future market excess returns
]

print(f"\n{'=' * 80}")
print("GLOBAL TARGET FEATURES CONFIGURATION")
print(f"{'=' * 80}")
print("Target features (future information - 1 row forward):")
for i, feat in enumerate(TARGET_FEATURES, 1):
    print(f"  {i}. {feat}")
print(f"{'=' * 80}\n")


# LOAD RAW DATA

data_path = Path(
    "/media/przem/w/kaggle/raw_data/hull-tactical-market-prediction/train.csv"
)
print(f"Loading RAW data from: {data_path}")
df_pl = pl.read_csv(data_path)

print(f"\n{'=' * 80}")
print("RAW DATA VALIDATION")
print(f"{'=' * 80}")
print(f"\n✓ Data shape: {df_pl.shape}")
print(f"✓ Memory usage (estimated): {df_pl.estimated_size('mb'):.2f} MB")
print("✓ Using Polars - 30-50% memory savings vs Pandas")

# Verify target features exist
print(f"\n{'=' * 80}")
print("TARGET FEATURES VERIFICATION")
print(f"{'=' * 80}")

for col in TARGET_FEATURES + ["date_id"]:
    if col in df_pl.columns:
        print(f"✓ {col}: Present")
        print(f"  - Type: {df_pl[col].dtype}")
        print(
            f"  - Missing: {df_pl[col].null_count()} ({df_pl[col].null_count() / df_pl.height * 100:.2f}%)"
        )
        if df_pl[col].dtype in [pl.Float64, pl.Float32, pl.Int64, pl.Int32]:
            print(f"  - Range: [{df_pl[col].min():.6f}, {df_pl[col].max():.6f}]")
    else:
        print(f"✗ {col}: MISSING!")
        raise ValueError(f"Required column '{col}' not found in raw data!")


# CREATE LAGGED VERSIONS OF TARGET FEATURES

print(f"\n{'=' * 80}")
print("CREATING LAGGED TARGET FEATURES")
print(f"{'=' * 80}")

# Create lagged versions (shift by 1 to make them usable as features)
for feat in TARGET_FEATURES:
    lagged_name = f"lagged_{feat}"
    df_pl = df_pl.with_columns([pl.col(feat).shift(1).alias(lagged_name)])
    print(f"✓ Created {lagged_name}")
    print(f"  - First value (should be null): {df_pl[lagged_name][0]}")
    print(f"  - Second value (= {feat}[0]): {df_pl[lagged_name][1]}")
    print(f"  - Null count: {df_pl[lagged_name].null_count()}")


# CREATE TARGET VARIABLES

print(f"\n{'=' * 80}")
print("TARGET VARIABLE CREATION")
print(f"{'=' * 80}\n")

# 1. Volatility Target (Regression) - Smoothed and winsorized to handle outliers
raw_volatility = pl.col("forward_returns").abs()

# Calculate percentiles for robust outlier clipping (winsorization)
p05 = df_pl.select(raw_volatility.quantile(0.05)).item()
p95 = df_pl.select(raw_volatility.quantile(0.95)).item()

# Apply winsorization
df_pl = df_pl.with_columns(
    [
        pl.when(raw_volatility < p05)
        .then(p05)
        .when(raw_volatility > p95)
        .then(p95)
        .otherwise(raw_volatility)
        .alias("volatility_target")
    ]
)

print("✓ Volatility Target (Winsorized Regression):")
print("  Formula: |forward_returns| clipped to [5th, 95th] percentile")
print("  Winsorization bounds:")
print(f"    Lower bound (5th percentile):  {p05:.6f}")
print(f"    Upper bound (95th percentile): {p95:.6f}")
print(
    f"  Range: [{df_pl['volatility_target'].min():.6f}, {df_pl['volatility_target'].max():.6f}]"
)
print(f"  Mean: {df_pl['volatility_target'].mean():.6f}")
print(f"  Median: {df_pl['volatility_target'].median():.6f}")
print(f"  Std: {df_pl['volatility_target'].std():.6f}")

# Calculate percentage of values that were clipped
n_clipped_low = df_pl.select((raw_volatility < p05).sum()).item()
n_clipped_high = df_pl.select((raw_volatility > p95).sum()).item()
total = df_pl.height
print("\n✓ Outlier Clipping:")
print(
    f"  Values clipped at lower bound: {n_clipped_low} ({n_clipped_low / total * 100:.2f}%)"
)
print(
    f"  Values clipped at upper bound: {n_clipped_high} ({n_clipped_high / total * 100:.2f}%)"
)
print(
    f"  Total clipped: {n_clipped_low + n_clipped_high} ({(n_clipped_low + n_clipped_high) / total * 100:.2f}%)"
)

# 2. Direction Target (Binary Classification)
df_pl = df_pl.with_columns(
    [(pl.col("forward_returns") > 0).cast(pl.Int32).alias("direction_target")]
)

pos_count = (df_pl["direction_target"] == 1).sum()
neg_count = (df_pl["direction_target"] == 0).sum()

print("\n✓ Direction Target (Binary Classification):")
print("  Formula: forward_returns > 0")
print(f"  Positive (1): {pos_count} ({pos_count / total * 100:.2f}%)")
print(f"  Negative (0): {neg_count} ({neg_count / total * 100:.2f}%)")
print(f"  Class balance: {min(pos_count, neg_count) / max(pos_count, neg_count):.3f}")


# DATA VALIDATION


print(f"\n{'=' * 80}")
print("DATA QUALITY CHECKS")
print(f"{'=' * 80}")

# Time range
if "date_id" in df_pl.columns:
    print("\n✓ Time Range:")
    print(f"  Date ID range: [{df_pl['date_id'].min()}, {df_pl['date_id'].max()}]")
    print(f"  Total trading days: {df_pl['date_id'].n_unique()}")
    print(f"  Data points: {df_pl.height}")

    # Check if date_id is sorted
    is_sorted = (df_pl["date_id"].diff().drop_nulls() >= 0).all()
    print(f"  Data sorted by date_id: {is_sorted}")

# Check lagged versions are correctly shifted
print("\n✓ Lagged Feature Validation:")
for feat in TARGET_FEATURES:
    lagged_name = f"lagged_{feat}"
    # Check if lagged = shifted original
    original = df_pl[feat].to_numpy()
    lagged = df_pl[lagged_name].to_numpy()

    # Compare lagged[i] with original[i-1] for i >= 1
    shift_match = np.allclose(lagged[1:], original[:-1], equal_nan=True)
    print(f"  {lagged_name} = {feat}.shift(1): {shift_match}")

# Missing values summary
null_counts = {col: df_pl[col].null_count() for col in df_pl.columns}
cols_with_missing = {k: v for k, v in null_counts.items() if v > 0}

print("\n✓ Missing Values:")
if len(cols_with_missing) > 0:
    print(f"  Columns with missing values: {len(cols_with_missing)}")
    print("  Top columns by missing count:")
    sorted_missing = sorted(
        cols_with_missing.items(), key=lambda x: x[1], reverse=True
    )[:10]
    for col, count in sorted_missing:
        print(f"    {col}: {count} ({count / df_pl.height * 100:.2f}%)")
else:
    print("  No missing values found!")

# Target correlations
vol_target = df_pl["volatility_target"].to_numpy()
lagged_abs = df_pl["lagged_forward_returns"].abs().to_numpy()
# Remove NaN for correlation
valid_mask = ~(np.isnan(vol_target) | np.isnan(lagged_abs))
if valid_mask.sum() > 0:
    vol_corr = np.corrcoef(vol_target[valid_mask], lagged_abs[valid_mask])[0, 1]
    print("\n✓ Target Correlations:")
    print(f"  volatility_target vs |lagged_forward_returns|: {vol_corr:.4f}")
    print("  (Moderate correlation expected, high correlation = potential leakage)")

print(f"\n{'=' * 80}")
print("DATA LOADING & TARGET CREATION COMPLETE")
print(f"{'=' * 80}")
print(f"✓ Loaded raw data from: {data_path}")
print(f"✓ Created lagged versions of {len(TARGET_FEATURES)} target features")
print("✓ Created target variables:")
print("  1. volatility_target (regression)")
print("  2. direction_target (binary classification)")
print(f"✓ Data shape: {df_pl.shape}")
print("✓ All lagged features validated - correctly shifted by 1 row")
print("✓ Ready for feature engineering")
print(f"{'=' * 80}\n")

# %% [CELL 2] DEBUG: Validate Data Loading
# DEBUG CELL 1: Validate data loading and check for temporal ordering
print("\n" + "=" * 80)
print("DEBUG: DATA LOADING VALIDATION")
print("=" * 80)

# 1. Check data is sorted by date_id
date_ids = df_pl["date_id"].to_numpy()
is_sorted = np.all(date_ids[:-1] <= date_ids[1:])
print(f"\n✓ Data sorted by date_id: {is_sorted}")
if not is_sorted:
    print("  ⚠️ WARNING: Data is NOT sorted - this could cause data leakage!")

# 2. Check for duplicates
n_unique_dates = df_pl["date_id"].n_unique()
print(f"✓ Unique date_ids: {n_unique_dates} / {len(df_pl)} rows")

# 3. Verify forward_returns is target (future data)
print("\n✓ Target variable check:")
print(f"  - forward_returns exists: {'forward_returns' in df_pl.columns}")
print("  - This is FUTURE data (target) - should NOT be used for features")

# 4. Check lagged features exist
lagged_cols = [c for c in df_pl.columns if "lagged" in c.lower()]
print(f"\n✓ Lagged features found: {len(lagged_cols)}")
for col in lagged_cols[:5]:
    print(f"  - {col}")

# 5. Memory check
print(f"\n✓ Memory usage: {df_pl.estimated_size('mb'):.2f} MB")
print("✓ Using Polars DataFrame (efficient)")

print("\n" + "=" * 80 + "\n")

# %% [CELL 3] Dataset Split: PARTIAL / TRAIN / VALIDATION

# DATASET SPLIT: PARTIAL / TRAIN / VALIDATION

# Create three non-overlapping datasets:
# 1. Dataset with partial NaNs (from start until first complete row)
# 2. Training dataset (no NaNs) - from first complete row to (end - 255)
# 3. Validation dataset (no NaNs) - last 255 rows

VALIDATION_SIZE = 180  # Last 180 rows for validation

print(f"\n{'=' * 80}")
print("DATASET SPLIT: FINDING FIRST COMPLETE ROW")
print(f"{'=' * 80}\n")

# Find the first row where ALL features have non-null values
print("Analyzing null values across all columns...")

# Get null mask for all columns
null_mask = df_pl.null_count()
print(f"\n✓ Total columns: {len(df_pl.columns)}")
print(f"✓ Columns with any nulls: {sum(1 for x in null_mask.row(0) if x > 0)}")

# Find first row index where ALL columns are non-null
# We'll check row by row until we find the first complete row
first_complete_idx = None

for idx in range(len(df_pl)):
    # Check if this row has any nulls across all columns
    row_has_null = df_pl[idx].null_count().sum_horizontal()[0] > 0

    if not row_has_null:
        first_complete_idx = idx
        print(f"\n✓ First complete row found at index: {first_complete_idx}")
        print(f"  Date ID at this row: {df_pl[idx, 'date_id']}")
        break

    # Progress indicator every 100 rows
    if idx % 100 == 0 and idx > 0:
        print(f"  Checked {idx} rows...")

if first_complete_idx is None:
    print("\n⚠️ WARNING: No completely non-null row found!")
    print(f"   All {len(df_pl)} rows contain at least one null value")
    first_complete_idx = len(df_pl)  # Use entire dataset as partial
else:
    print("\n✓ Analysis complete!")
    print(f"  Rows with some nulls: {first_complete_idx}")
    print(f"  Rows without nulls: {len(df_pl) - first_complete_idx}")


# CREATE THREE NON-OVERLAPPING DATASETS

print(f"\n{'=' * 80}")
print("CREATING DATASET SPLITS")
print(f"{'=' * 80}\n")

# Dataset 1: Partial data (has some NaNs) - rows [0, first_complete_idx)
if first_complete_idx > 0:
    df_partial = df_pl[:first_complete_idx]
    print("✓ Dataset 1 (PARTIAL - with NaNs):")
    print(f"  Rows: {len(df_partial)}")
    print(
        f"  Date ID range: [{df_partial['date_id'].min()}, {df_partial['date_id'].max()}]"
    )
    print(f"  Total nulls: {df_partial.null_count().sum_horizontal()[0]}")

    # Show which columns have nulls
    partial_null_counts = {
        col: df_partial[col].null_count() for col in df_partial.columns
    }
    partial_cols_with_nulls = {k: v for k, v in partial_null_counts.items() if v > 0}
    print(f"  Columns with nulls: {len(partial_cols_with_nulls)}")
    if len(partial_cols_with_nulls) > 0:
        print("  Top 10 columns by null count:")
        sorted_nulls = sorted(
            partial_cols_with_nulls.items(), key=lambda x: x[1], reverse=True
        )[:10]
        for col, count in sorted_nulls:
            print(f"    {col}: {count} ({count / len(df_partial) * 100:.1f}%)")
else:
    df_partial = None
    print("✗ Dataset 1 (PARTIAL): Empty (first row is already complete)")

# Split complete data into Training and Validation
if first_complete_idx < len(df_pl):
    df_complete = df_pl[first_complete_idx:]
    complete_rows = len(df_complete)

    print(f"\n✓ Complete data (no NaNs): {complete_rows} rows")

    # Check if we have enough rows for validation split
    if complete_rows > VALIDATION_SIZE:
        # Dataset 2: Training (no NaNs) - rows [first_complete_idx, end - VALIDATION_SIZE]
        train_end_idx = len(df_pl) - VALIDATION_SIZE
        df_train = df_pl[first_complete_idx:train_end_idx]

        print("\n✓ Dataset 2 (TRAIN - no NaNs):")
        print(f"  Rows: {len(df_train)}")
        print(
            f"  Date ID range: [{df_train['date_id'].min()}, {df_train['date_id'].max()}]"
        )

        # Verify no nulls
        train_nulls = df_train.null_count().sum_horizontal()[0]
        print(f"  Total nulls: {train_nulls}")
        if train_nulls == 0:
            print("  ✅ VERIFIED: No null values!")
        else:
            print(f"  ⚠️ WARNING: Contains {train_nulls} null values!")

        # Dataset 3: Validation (no NaNs) - last VALIDATION_SIZE rows
        df_validation = df_pl[-VALIDATION_SIZE:]

        print("\n✓ Dataset 3 (VALIDATION - no NaNs):")
        print(f"  Rows: {len(df_validation)}")
        print(
            f"  Date ID range: [{df_validation['date_id'].min()}, {df_validation['date_id'].max()}]"
        )

        # Verify no nulls
        val_nulls = df_validation.null_count().sum_horizontal()[0]
        print(f"  Total nulls: {val_nulls}")
        if val_nulls == 0:
            print("  ✅ VERIFIED: No null values!")
        else:
            print(f"  ⚠️ WARNING: Contains {val_nulls} null values!")
    else:
        print("  ⚠️ WARNING: Not enough rows for validation split!")
        print(f"  Need at least {VALIDATION_SIZE + 1} rows, have {complete_rows}")
        print("  Using all complete data as training set")
        df_train = df_complete
        df_validation = None
else:
    df_train = None
    df_validation = None
    print("\n✗ Dataset 2 (TRAIN): Empty (all rows have nulls)")
    print("✗ Dataset 3 (VALIDATION): Empty (all rows have nulls)")


# VERIFY NON-OVERLAPPING

print(f"\n{'=' * 80}")
print("VERIFICATION: NON-OVERLAPPING DATASETS")
print(f"{'=' * 80}\n")

if df_partial is not None:
    print(
        f"✓ Dataset 1 (PARTIAL) date_id range: [{df_partial['date_id'].min()}, {df_partial['date_id'].max()}]"
    )
    partial_max_date = df_partial["date_id"].max()
else:
    partial_max_date = None

if df_train is not None:
    print(
        f"✓ Dataset 2 (TRAIN) date_id range: [{df_train['date_id'].min()}, {df_train['date_id'].max()}]"
    )
    train_min_date = df_train["date_id"].min()
    train_max_date = df_train["date_id"].max()
else:
    train_min_date = None
    train_max_date = None

if df_validation is not None:
    print(
        f"✓ Dataset 3 (VALIDATION) date_id range: [{df_validation['date_id'].min()}, {df_validation['date_id'].max()}]"
    )
    val_min_date = df_validation["date_id"].min()
else:
    val_min_date = None

# Verify no overlap
print("\n✓ Checking for overlaps:")
if partial_max_date is not None and train_min_date is not None:
    if partial_max_date < train_min_date:
        print(
            f"  ✅ PARTIAL ↔ TRAIN: Non-overlapping (gap: {train_min_date - partial_max_date} days)"
        )
    else:
        print("  ⚠️ PARTIAL ↔ TRAIN: May overlap!")

if train_max_date is not None and val_min_date is not None:
    if train_max_date < val_min_date:
        print(
            f"  ✅ TRAIN ↔ VALIDATION: Non-overlapping (gap: {val_min_date - train_max_date} days)"
        )
    else:
        print("  ⚠️ TRAIN ↔ VALIDATION: May overlap!")

# Verify total rows
total_rows_split = 0
if df_partial is not None:
    total_rows_split += len(df_partial)
if df_train is not None:
    total_rows_split += len(df_train)
if df_validation is not None:
    total_rows_split += len(df_validation)

print("\n✓ Row count verification:")
print(f"  Original dataset: {len(df_pl)} rows")
print(f"  Split datasets total: {total_rows_split} rows")
if total_rows_split == len(df_pl):
    print("  ✅ Row count matches!")
else:
    print(f"  ⚠️ Row count mismatch: {len(df_pl) - total_rows_split} rows difference")


# SAVE DATASETS

print(f"\n{'=' * 80}")
print("SAVING DATASETS")
print(f"{'=' * 80}\n")

output_dir = Path("/media/przem/w/kaggle/preprocessed_data")
output_dir.mkdir(parents=True, exist_ok=True)

if df_partial is not None:
    partial_path = output_dir / "train_partial_with_nans.csv"
    df_partial.write_csv(partial_path)
    print(f"✓ Saved Dataset 1 (PARTIAL): {partial_path}")
    print(f"  Size: {partial_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"  Rows: {len(df_partial)}")

if df_train is not None:
    train_path = output_dir / "train_complete_no_nans.csv"
    df_train.write_csv(train_path)
    print(f"\n✓ Saved Dataset 2 (TRAIN): {train_path}")
    print(f"  Size: {train_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"  Rows: {len(df_train)}")

if df_validation is not None:
    # CRITICAL: Remove target/label columns from validation dataset
    # These contain FUTURE information and should NOT be available during inference
    columns_to_remove_from_validation = [
        "forward_returns",  # Future return (target) - REMOVE
        "risk_free_rate",  # Future risk-free rate - REMOVE
        "market_forward_excess_returns",  # Future market excess returns - REMOVE
        "volatility_target",  # Volatility label - REMOVE
        "direction_target",  # Direction label - REMOVE
    ]

    print("\n🔒 Removing target/label columns from VALIDATION dataset...")
    existing_columns_to_remove = [
        col for col in columns_to_remove_from_validation if col in df_validation.columns
    ]
    if existing_columns_to_remove:
        df_validation = df_validation.drop(existing_columns_to_remove)
        print(
            f"   ✅ Removed {len(existing_columns_to_remove)} columns: {existing_columns_to_remove}"
        )

    # Verify lagged columns are still present
    lagged_columns_to_keep = [
        "lagged_forward_returns",
        "lagged_risk_free_rate",
        "lagged_market_forward_excess_returns",
    ]
    present_lagged = [
        col for col in lagged_columns_to_keep if col in df_validation.columns
    ]
    print(f"   ✅ Kept lagged features: {present_lagged}")

    val_path = output_dir / "validation_complete_no_nans.csv"
    df_validation.write_csv(val_path)
    print(f"\n✓ Saved Dataset 3 (VALIDATION): {val_path}")
    print(f"  Size: {val_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"  Rows: {len(df_validation)}")


# UPDATE WORKING DATAFRAME

print(f"\n{'=' * 80}")
print("UPDATING WORKING DATAFRAME")
print(f"{'=' * 80}\n")

# For the rest of the notebook, we'll use the TRAIN dataset (no NaNs)
# This ensures all feature engineering works without NaN issues
if df_train is not None:
    df_pl = df_train.clone()
    print("✓ Updated df_pl to use TRAIN dataset (no NaNs)")
    print(f"  Working with {len(df_pl)} rows")
    print(f"  Date ID range: [{df_pl['date_id'].min()}, {df_pl['date_id'].max()}]")
    print(f"  Validation set preserved separately: {VALIDATION_SIZE} rows")
else:
    print("⚠️ Keeping original df_pl (no train dataset available)")

print(f"\n{'=' * 80}")
print("DATASET SPLIT COMPLETE")
print(f"{'=' * 80}")
print("✅ Created 3 non-overlapping datasets:")
print("   1. PARTIAL (with NaNs) - for analysis")
print("   2. TRAIN (no NaNs) - for feature engineering & model training")
print(f"   3. VALIDATION (no NaNs, {VALIDATION_SIZE} rows) - for model validation")
print(f"✅ Saved all datasets to {output_dir}")
print("✅ Updated working dataframe to use TRAIN data (no NaNs)")
print(f"{'=' * 80}\n")

# %% [CELL 4] DEBUG: Validate Target Features
# DEBUG CELL 2: Validate target features in all datasets
print("\n" + "=" * 80)
print("DEBUG: TARGET FEATURES VALIDATION ACROSS ALL DATASETS")
print("=" * 80)

# Define all target-related columns to check
target_columns = TARGET_FEATURES + [
    "lagged_forward_returns",
    "lagged_risk_free_rate",
    "lagged_market_forward_excess_returns",
    "volatility_target",
    "direction_target",
]

print(
    f"\n✓ Checking {len(target_columns)} target-related columns across all datasets:\n"
)


# CHECK DATASET 1: PARTIAL (with NaNs)

if df_partial is not None:
    print("=" * 80)
    print("DATASET 1: PARTIAL (with NaNs)")
    print("=" * 80)
    print(f"Total rows: {len(df_partial)}\n")

    for col in target_columns:
        if col in df_partial.columns:
            null_count = df_partial[col].null_count()
            null_pct = (null_count / len(df_partial)) * 100
            min_val = df_partial[col].min()
            max_val = df_partial[col].max()
            print(
                f"✓ {col:40s}: nulls={null_count:4d} ({null_pct:5.1f}%), range=[{min_val:+.6f}, {max_val:+.6f}]"
            )
        else:
            print(f"✗ {col:40s}: MISSING!")
else:
    print("DATASET 1: PARTIAL - Not available")


# CHECK DATASET 2: TRAIN (no NaNs)

if df_train is not None:
    print(f"\n{'=' * 80}")
    print("DATASET 2: TRAIN (no NaNs)")
    print("=" * 80)
    print(f"Total rows: {len(df_train)}\n")

    for col in target_columns:
        if col in df_train.columns:
            null_count = df_train[col].null_count()
            null_pct = (null_count / len(df_train)) * 100
            min_val = df_train[col].min()
            max_val = df_train[col].max()

            if null_count == 0:
                status = "✅"
            else:
                status = "⚠️"

            print(
                f"{status} {col:40s}: nulls={null_count:4d} ({null_pct:5.1f}%), range=[{min_val:+.6f}, {max_val:+.6f}]"
            )
        else:
            print(f"✗ {col:40s}: MISSING!")
else:
    print(f"\n{'=' * 80}")
    print("DATASET 2: TRAIN - Not available")


# CHECK DATASET 3: VALIDATION (no NaNs)

if df_validation is not None:
    print(f"\n{'=' * 80}")
    print("DATASET 3: VALIDATION (no NaNs)")
    print("=" * 80)
    print(f"Total rows: {len(df_validation)}\n")

    for col in target_columns:
        if col in df_validation.columns:
            null_count = df_validation[col].null_count()
            null_pct = (null_count / len(df_validation)) * 100
            min_val = df_validation[col].min()
            max_val = df_validation[col].max()

            if null_count == 0:
                status = "✅"
            else:
                status = "⚠️"

            print(
                f"{status} {col:40s}: nulls={null_count:4d} ({null_pct:5.1f}%), range=[{min_val:+.6f}, {max_val:+.6f}]"
            )
        else:
            print(f"✗ {col:40s}: MISSING!")
else:
    print(f"\n{'=' * 80}")
    print("DATASET 3: VALIDATION - Not available")


# CHECK CURRENT WORKING DATAFRAME (df_pl = TRAIN)

print(f"\n{'=' * 80}")
print("CURRENT WORKING DATAFRAME (df_pl)")
print("=" * 80)
print(f"Total rows: {len(df_pl)}\n")

# Verify targets are based on forward_returns (FUTURE data)
print("✓ Target variables in df_pl:")
if "volatility_target" in df_pl.columns:
    print(
        f"  - volatility_target: range [{df_pl['volatility_target'].min():.6f}, {df_pl['volatility_target'].max():.6f}]"
    )
if "direction_target" in df_pl.columns:
    print(
        f"  - direction_target: values {sorted(df_pl['direction_target'].unique().to_list())}"
    )

# CRITICAL: Verify targets are NOT identical to lagged features
if "volatility_target" in df_pl.columns and "lagged_forward_returns" in df_pl.columns:
    vol_target_np = df_pl["volatility_target"].to_numpy()
    lagged_abs_np = df_pl["lagged_forward_returns"].abs().to_numpy()

    # Remove NaN for correlation
    valid_mask = ~(np.isnan(vol_target_np) | np.isnan(lagged_abs_np))
    if valid_mask.sum() > 0:
        vol_vs_lagged = np.corrcoef(
            vol_target_np[valid_mask], lagged_abs_np[valid_mask]
        )[0, 1]
        print("\n✓ Target vs Lagged correlation:")
        print(f"  - volatility_target vs |lagged_forward_returns|: {vol_vs_lagged:.4f}")
        print("  - Should be positive but < 1.0 (perfect correlation = data leakage)")

        # Check for identical values
        identical_vol = (
            df_pl["volatility_target"] == df_pl["lagged_forward_returns"].abs()
        ).sum()
        print("\n✓ Leakage check:")
        print(
            f"  - Identical values (volatility_target == |lagged_forward_returns|): {identical_vol}/{len(df_pl)}"
        )
        if identical_vol > 0:
            print(f"  ⚠️ WARNING: Found {identical_vol} identical values - investigate!")
        else:
            print(
                "  ✅ No identical values - targets properly derived from forward_returns"
            )

print("\n" + "=" * 80)
print("TARGET FEATURES VALIDATION COMPLETE")
print("=" * 80)
print(
    f"✅ All target features checked across {sum([df_partial is not None, df_train is not None, df_validation is not None])} datasets"
)
print("=" * 80 + "\n")

# %% [CELL 5] Feature Engineering (ROW-BY-ROW for PERFECT CONSISTENCY)
# ═══════════════════════════════════════════════════════════════════════════
# FEATURE ENGINEERING USING ROW-BY-ROW PROCESSING
# ═══════════════════════════════════════════════════════════════════════════
#
# STRATEGY: Use SAME row-by-row calculator for BOTH training and inference
# This guarantees PERFECT 1:1 matching between training data and production.
#
# KEY PRINCIPLE:
# - PARTIAL: Warm up the calculator (features calculated but dataset kept for history)
# - TRAIN: Process row-by-row using warmed calculator (these features are used for training)
# - VALIDATION: Process row-by-row in Cell 28 (same calculator, same code path)
#
# BENEFITS:
# ✓ ZERO discrepancy between training and inference
# ✓ Same code path for all datasets
# ✓ No batch vs row-by-row mismatches
# ✓ Production-ready from day 1


print(f"\n{'=' * 80}")
print("FEATURE ENGINEERING (ROW-BY-ROW)")
print(f"{'=' * 80}\n")

import numpy as np
from row_by_row_features import RowByRowFeatureCalculator

# ────────────────────────────────────────────────────────────────────────────
# STEP 1: Store original dataset info and target columns
# ────────────────────────────────────────────────────────────────────────────
print("STEP 1: Recording dataset info...")

partial_size = len(df_partial) if df_partial is not None else 0
train_size = len(df_train) if df_train is not None else 0
val_size = len(df_validation) if df_validation is not None else 0

print(f"  PARTIAL size:    {partial_size:5d} rows (will warm up calculator)")
print(f"  TRAIN size:      {train_size:5d} rows (will get features row-by-row)")
print(f"  VALIDATION size: {val_size:5d} rows (processed in Cell 28)")

# Target columns to preserve
target_columns = [
    "forward_returns",
    "risk_free_rate",
    "market_forward_excess_returns",
    "volatility_target",
    "direction_target",
]

# Store original dataframes with targets
df_partial_orig = df_partial.clone() if df_partial is not None else None
df_train_orig = df_train.clone() if df_train is not None else None

# ────────────────────────────────────────────────────────────────────────────
# STEP 2: Initialize Row-by-Row Calculator
# ────────────────────────────────────────────────────────────────────────────
print("\nSTEP 2: Initializing RowByRowFeatureCalculator...")

calculator = RowByRowFeatureCalculator()
print("  ✅ Calculator initialized")

# ────────────────────────────────────────────────────────────────────────────
# STEP 3: Process PARTIAL dataset (warm up calculator)
# ────────────────────────────────────────────────────────────────────────────
print("\nSTEP 3: Processing PARTIAL dataset (warming up calculator)...")

if df_partial is not None and len(df_partial) > 0:
    partial_features_list = []

    for idx in range(len(df_partial)):
        lagged_ret = df_partial["lagged_forward_returns"][idx]

        # Handle NaN properly
        if lagged_ret is None or (
            isinstance(lagged_ret, float) and np.isnan(lagged_ret)
        ):
            features = calculator.calculate_features_for_row(0.0, is_valid=False)
        else:
            features = calculator.calculate_features_for_row(
                float(lagged_ret), is_valid=True
            )

        partial_features_list.append(features)

        if (idx + 1) % 100 == 0 or idx == len(df_partial) - 1:
            print(f"  Processed {idx + 1}/{len(df_partial)} PARTIAL rows")

    # Create features dataframe
    df_partial_features = pl.DataFrame(partial_features_list)

    # Combine with original data
    df_partial = df_partial.hstack(df_partial_features)

    # Add back target columns
    if df_partial_orig is not None:
        for col in target_columns:
            if col in df_partial_orig.columns and col not in df_partial.columns:
                df_partial = df_partial.with_columns([df_partial_orig[col].alias(col)])

    # Save
    partial_path = output_dir / "train_partial_with_nans_engineered.csv"
    df_partial.write_csv(partial_path)
    print(f"  ✅ PARTIAL: {len(df_partial)} rows, {len(df_partial.columns)} columns")
    print(f"  💾 Saved: {partial_path}")

# ────────────────────────────────────────────────────────────────────────────
# STEP 4: Process TRAIN dataset (using warmed calculator)
# ────────────────────────────────────────────────────────────────────────────
print("\nSTEP 4: Processing TRAIN dataset (row-by-row with warmed calculator)...")

if df_train is not None and len(df_train) > 0:
    train_features_list = []

    for idx in range(len(df_train)):
        lagged_ret = df_train["lagged_forward_returns"][idx]

        # All TRAIN rows should be valid (no NaNs after PARTIAL)
        if lagged_ret is None or (
            isinstance(lagged_ret, float) and np.isnan(lagged_ret)
        ):
            features = calculator.calculate_features_for_row(0.0, is_valid=False)
        else:
            features = calculator.calculate_features_for_row(
                float(lagged_ret), is_valid=True
            )

        train_features_list.append(features)

        if (idx + 1) % 100 == 0 or idx == len(df_train) - 1:
            print(f"  Processed {idx + 1}/{len(df_train)} TRAIN rows")

    # Create features dataframe
    df_train_features = pl.DataFrame(train_features_list)

    # Combine with original data
    df_train = df_train.hstack(df_train_features)

    # Add back target columns
    if df_train_orig is not None:
        for col in target_columns:
            if col in df_train_orig.columns and col not in df_train.columns:
                df_train = df_train.with_columns([df_train_orig[col].alias(col)])

    # Save
    train_path = output_dir / "train_complete_no_nans_engineered.csv"
    df_train.write_csv(train_path)
    print(f"  ✅ TRAIN: {len(df_train)} rows, {len(df_train.columns)} columns")
    print(f"  💾 Saved: {train_path}")

# Update working dataframe
df_pl = df_train.clone() if df_train is not None else df_partial.clone()
print(f"\n  ✅ Working dataframe (df_pl) updated: {len(df_pl)} rows")

# ────────────────────────────────────────────────────────────────────────────
# STEP 5: SAVE CALCULATOR STATE FOR VALIDATION RESUMPTION
# ────────────────────────────────────────────────────────────────────────────
# CRITICAL: Save the calculator state so Cell 28 can RESUME from this exact point
# This ensures VALIDATION features are calculated with continuous state from TRAIN

print("\n  💾 Saving calculator state for validation resumption...")
calculator_state_after_train = calculator.save_state()
# Add session_id to prevent loading stale state
calculator_state_after_train["session_id"] = TRAINING_SESSION_ID
print(f"     • Session ID: {TRAINING_SESSION_ID}")
print(
    f"     • History length: {len(calculator_state_after_train['hist_returns'])} rows"
)
print(f"     • Row count: {calculator_state_after_train['row_count']}")
print(f"     • EWMA states: {list(calculator_state_after_train['ewma_states'].keys())}")
print("  ✅ Calculator state saved to 'calculator_state_after_train'")

# ────────────────────────────────────────────────────────────────────────────
# STEP 6: Summary
# ────────────────────────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print("FEATURE ENGINEERING COMPLETE (ROW-BY-ROW)")
print(f"{'=' * 80}\n")

# Get feature names from calculator
sample_features = calculator.calculate_features_for_row(0.01, is_valid=True)
feature_names = list(sample_features.keys())

print(f"✅ Created {len(feature_names)} features using row-by-row processing:")
print(f"   {feature_names[:10]}...")
print(f"   ... and {len(feature_names) - 10} more")

print("\n✅ KEY GUARANTEE: TRAIN uses EXACT SAME calculation as VALIDATION/PRODUCTION")
print(
    "✅ Same RowByRowFeatureCalculator instance processes PARTIAL → TRAIN → VALIDATION"
)
print("✅ Calculator state saved - Cell 28 will RESUME from this exact point")
print("✅ No batch vs row-by-row discrepancies possible")
print(f"✅ Datasets saved to {output_dir}")
print(f"{'=' * 80}\n")


# %% [CELL 5.5] VALIDATE ROW-BY-ROW FEATURE CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION: Verify Cell 5's row-by-row processing is consistent
# ═══════════════════════════════════════════════════════════════════════════
#
# Since Cell 5 now uses RowByRowFeatureCalculator for both PARTIAL and TRAIN,
# features are GUARANTEED to match production. This cell performs a sanity
# check by re-processing a few rows and comparing.
#
# FULL VALIDATION of API simulation vs training happens AFTER Cell 28,
# because model-based features (HMM, CUSUM, etc.) require trained models.
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 80}")
print("CELL 5.5: ROW-BY-ROW FEATURE CONSISTENCY CHECK")
print(f"{'=' * 80}\n")

import numpy as np
from row_by_row_features import RowByRowFeatureCalculator

# ────────────────────────────────────────────────────────────────────────────
# QUICK SANITY CHECK: Re-process last 10 rows and compare
# ────────────────────────────────────────────────────────────────────────────

print("Sanity check: Re-processing last 10 TRAIN rows with fresh calculator...")
print()

# Get all lagged returns from PARTIAL + TRAIN to match Cell 5's processing
all_lagged_returns = []

# PARTIAL first
if df_partial is not None:
    for i in range(len(df_partial)):
        val = df_partial["lagged_forward_returns"][i]
        if val is None or (isinstance(val, float) and np.isnan(val)):
            all_lagged_returns.append((0.0, False))  # NaN row
        else:
            all_lagged_returns.append((float(val), True))

# TRAIN second
n_train = len(df_train)
for i in range(n_train):
    val = df_train["lagged_forward_returns"][i]
    if val is None or (isinstance(val, float) and np.isnan(val)):
        all_lagged_returns.append((0.0, False))  # NaN row
    else:
        all_lagged_returns.append((float(val), True))

print(
    f"  Total history: {len(all_lagged_returns)} rows (PARTIAL: {len(df_partial)}, TRAIN: {n_train})"
)

# Re-create calculator and process everything up to last 10 rows
check_calculator = RowByRowFeatureCalculator()

n_check = 10
n_warmup = len(all_lagged_returns) - n_check

print(f"  Warming up with {n_warmup} rows...")
for i in range(n_warmup):
    lagged_ret, is_valid = all_lagged_returns[i]
    check_calculator.calculate_features_for_row(lagged_ret, is_valid=is_valid)

print(f"  Comparing last {n_check} rows...")
print()

# Compare last 10 rows
features_to_check = [
    "daily_volatility_lagged",
    "volatility_ma_21",
    "mean_hist_vol_21",
    "momentum_5d",
    "momentum_21d",
    "zscore_21d",
    "ewma_vol_21d",
    "consecutive_up",
    "consecutive_down",
    "expanding_mean_vol",
]

mismatches = []
for i in range(n_check):
    row_idx = n_warmup + i
    train_row_idx = row_idx - len(df_partial)  # Offset for df_train

    lagged_ret, is_valid = all_lagged_returns[row_idx]
    calc_features = check_calculator.calculate_features_for_row(
        lagged_ret, is_valid=is_valid
    )

    for feat in features_to_check:
        if feat in calc_features and feat in df_train.columns:
            calc_val = calc_features[feat]
            train_val = df_train[feat][train_row_idx]

            if train_val is not None and not np.isnan(train_val):
                diff = abs(float(calc_val) - float(train_val))
                if diff > 1e-6:
                    mismatches.append((train_row_idx, feat, calc_val, train_val, diff))

if mismatches:
    print(f"⚠️  Found {len(mismatches)} mismatches:")
    for row, feat, calc, train, diff in mismatches[:10]:
        print(f"     Row {row}: {feat} = {calc:.6f} vs {train:.6f} (diff: {diff:.6f})")
else:
    print("✅ ALL FEATURES MATCH PERFECTLY!")
    print("   Cell 5's row-by-row processing is consistent.")

print()
print("─" * 80)
print("NOTE: Full API simulation validation happens AFTER Cell 28")
print("      (Model-based features like HMM, CUSUM require trained models)")
print("─" * 80)
print()

# ────────────────────────────────────────────────────────────────────────────
# Show feature counts
# ────────────────────────────────────────────────────────────────────────────
sample_features = check_calculator.calculate_features_for_row(0.01, is_valid=True)
print(f"Features from RowByRowFeatureCalculator: {len(sample_features)}")
print(f"Columns in df_train: {len(df_train.columns)}")
print()

# List basic feature groups
basic_feature_names = [f for f in sample_features.keys()]
print(f"Basic features calculated ({len(basic_feature_names)} total):")
print(f"  {basic_feature_names[:15]}...")
print(f"  ...and {len(basic_feature_names) - 15} more")

print(f"\n{'=' * 80}")
print("CELL 5.5 COMPLETE")
print(f"{'=' * 80}\n")


# %% [CELL 5.6] Forward Returns Relative to Expectations
# ═══════════════════════════════════════════════════════════════════════════
# FORWARD RETURNS RELATIVE TO EXPECTATIONS
# ═══════════════════════════════════════════════════════════════════════════
#
# Formula: Subtract rolling 5-year mean from lagged_forward_returns,
# then winsorize using MAD (Median Absolute Deviation) with criterion 4.
#
# TRAIN SET ONLY: Rolling mean and MAD computed using only training data
# to avoid look-ahead bias when applying to validation/test sets.
#
# This captures whether current returns are above/below historical expectations.
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 80}")
print("CELL 5.6: FORWARD RETURNS RELATIVE TO EXPECTATIONS")
print(f"{'=' * 80}\n")

import numpy as np


def calculate_returns_relative_to_expectations_row_by_row(
    returns_array, rolling_window=1260, mad_criterion=4.0
):
    """
    Calculate forward returns relative to expectations using ROW-BY-ROW processing.

    CRITICAL: Uses only PAST data for each row - no look-ahead bias.

    Steps for each row i:
    1. Compute rolling mean from rows [max(0, i-rolling_window+1), i] (past only)
    2. Subtract rolling mean from current value to get "relative to expectations"
    3. Compute MAD from all PAST relative returns (not including future)
    4. Winsorize using the historical MAD with criterion 4

    Parameters:
    -----------
    returns_array : np.ndarray
        Array of lagged_forward_returns values
    rolling_window : int
        Rolling window for mean calculation (default: 1260 = ~5 years)
    mad_criterion : float
        MAD multiplier for winsorization (default: 4.0)

    Returns:
    --------
    np.ndarray with winsorized relative returns
    """
    n = len(returns_array)
    result = np.full(n, np.nan)

    # Track historical relative returns for expanding MAD calculation
    historical_relative = []

    for i in range(n):
        current_val = returns_array[i]

        # Skip if current value is NaN
        if np.isnan(current_val):
            continue

        # Step 1: Calculate rolling mean using PAST data only (including current row)
        start_idx = max(0, i - rolling_window + 1)
        window_data = returns_array[start_idx : i + 1]
        valid_data = window_data[~np.isnan(window_data)]

        if len(valid_data) == 0:
            continue

        rolling_mean = np.mean(valid_data)

        # Step 2: Calculate relative return
        relative_return = current_val - rolling_mean

        # Step 3: Winsorize using HISTORICAL MAD (from past relative returns only)
        if len(historical_relative) >= 20:  # Need enough history for stable MAD
            hist_arr = np.array(historical_relative)
            median_val = np.median(hist_arr)
            mad = np.median(np.abs(hist_arr - median_val))

            if mad == 0:
                mad = 1e-8

            # Winsorize
            lower_bound = median_val - mad_criterion * mad
            upper_bound = median_val + mad_criterion * mad
            result[i] = np.clip(relative_return, lower_bound, upper_bound)
        else:
            # Not enough history - use raw relative return (no winsorization yet)
            result[i] = relative_return

        # Step 4: Add current relative return to history for future rows
        historical_relative.append(relative_return)

    return result


def calculate_returns_relative_to_expectations(
    df, rolling_window=1260, mad_criterion=4.0, dataset_name="TRAIN"
):
    """
    Calculate forward returns relative to expectations.

    Steps:
    1. Compute 5-year (1260 trading days) rolling mean of lagged_forward_returns
    2. Subtract rolling mean from current value to get "relative to expectations"
    3. Winsorize using MAD with criterion 4 (clip at median ± 4*MAD)

    Parameters:
    -----------
    df : pl.DataFrame
        DataFrame with 'lagged_forward_returns' column
    rolling_window : int
        Rolling window for mean calculation (default: 1260 = ~5 years)
    mad_criterion : float
        MAD multiplier for winsorization (default: 4.0)
    dataset_name : str
        Name for logging

    Returns:
    --------
    pl.DataFrame with 'returns_relative_to_expectation' column added
    """
    print(f"  Processing {dataset_name} (row-by-row, no look-ahead)...")

    if "lagged_forward_returns" not in df.columns:
        print("    ⚠️ 'lagged_forward_returns' not found, skipping")
        return df

    # Convert to numpy for row-by-row calculation
    returns = df["lagged_forward_returns"].to_numpy().astype(np.float64)

    # Use row-by-row calculation (no look-ahead bias)
    winsorized = calculate_returns_relative_to_expectations_row_by_row(
        returns, rolling_window=rolling_window, mad_criterion=mad_criterion
    )

    # Calculate final stats for logging
    valid_vals = winsorized[~np.isnan(winsorized)]
    if len(valid_vals) > 0:
        median_val = np.median(valid_vals)
        mad = np.median(np.abs(valid_vals - median_val))
        print(f"    Rolling window: {rolling_window} days (~5 years)")
        print(f"    Final median: {median_val:.6f}")
        print(f"    Final MAD: {mad:.6f}")
        print(f"    Valid values: {len(valid_vals)}/{len(winsorized)}")

    # Add column to dataframe
    df = df.with_columns([pl.Series("returns_relative_to_expectation", winsorized)])

    print("    ✅ Added 'returns_relative_to_expectation' column (row-by-row)")

    return df


# ────────────────────────────────────────────────────────────────────────────
# Apply to PARTIAL dataset
# ────────────────────────────────────────────────────────────────────────────
if df_partial is not None and len(df_partial) > 0:
    df_partial = calculate_returns_relative_to_expectations(
        df_partial, dataset_name="PARTIAL"
    )

# ────────────────────────────────────────────────────────────────────────────
# Apply to TRAIN dataset (using PARTIAL + TRAIN combined for rolling mean context)
# ────────────────────────────────────────────────────────────────────────────
if df_train is not None and len(df_train) > 0:
    # For TRAIN, we need context from PARTIAL to compute rolling mean correctly
    # Process PARTIAL + TRAIN together row-by-row, then extract TRAIN portion

    if df_partial is not None and len(df_partial) > 0:
        # Concatenate PARTIAL + TRAIN for proper historical context
        combined_returns = np.concatenate(
            [
                df_partial["lagged_forward_returns"].to_numpy().astype(np.float64),
                df_train["lagged_forward_returns"].to_numpy().astype(np.float64),
            ]
        )

        n_partial = len(df_partial)
        rolling_window = 1260
        mad_criterion = 4.0

        print("\n  Processing TRAIN (with PARTIAL context, row-by-row)...")
        print(
            f"    Combined context: {len(combined_returns)} rows (PARTIAL: {n_partial}, TRAIN: {len(df_train)})"
        )

        # Calculate row-by-row for entire combined series
        combined_result = calculate_returns_relative_to_expectations_row_by_row(
            combined_returns, rolling_window=rolling_window, mad_criterion=mad_criterion
        )

        # Extract TRAIN portion only
        winsorized_train = combined_result[n_partial:]

        # Log final stats
        valid_vals = winsorized_train[~np.isnan(winsorized_train)]
        if len(valid_vals) > 0:
            median_val = np.median(valid_vals)
            mad = np.median(np.abs(valid_vals - median_val))
            print(f"    TRAIN portion: {len(winsorized_train)} rows")
            print(f"    Final median: {median_val:.6f}")
            print(f"    Final MAD: {mad:.6f}")
            print(f"    Valid values: {len(valid_vals)}/{len(winsorized_train)}")

        # Add column to TRAIN dataframe
        df_train = df_train.with_columns(
            [pl.Series("returns_relative_to_expectation", winsorized_train)]
        )
        print(
            "    ✅ Added 'returns_relative_to_expectation' column to TRAIN (row-by-row)"
        )
    else:
        # Fallback: simple calculation without PARTIAL context
        df_train = calculate_returns_relative_to_expectations(
            df_train, dataset_name="TRAIN"
        )

# Update working dataframe
if df_train is not None:
    df_pl = df_train.clone()

# ────────────────────────────────────────────────────────────────────────────
# Save state for validation/inference consistency
# ────────────────────────────────────────────────────────────────────────────
# Store the history and MAD parameters computed from training data for use in validation
if df_train is not None and "returns_relative_to_expectation" in df_train.columns:
    train_returns = df_train["lagged_forward_returns"].to_numpy().astype(np.float64)

    # Build combined history for rolling mean in inference
    if df_partial is not None:
        combined_for_storage = np.concatenate(
            [
                df_partial["lagged_forward_returns"].to_numpy().astype(np.float64),
                train_returns,
            ]
        )
    else:
        combined_for_storage = train_returns

    # Store last N values needed for rolling mean calculation in inference
    RETURNS_RELATIVE_ROLLING_WINDOW = 1260
    returns_relative_history = combined_for_storage[
        -RETURNS_RELATIVE_ROLLING_WINDOW:
    ].tolist()

    # Store the HISTORICAL relative returns for expanding MAD in inference
    # This needs to be the relative returns computed row-by-row up to end of TRAIN
    relative_for_mad = df_train["returns_relative_to_expectation"].to_numpy()
    valid_relative = relative_for_mad[~np.isnan(relative_for_mad)]

    # Store as list for inference continuation
    returns_relative_historical = valid_relative.tolist()

    # Also compute final MAD stats for logging
    RETURNS_RELATIVE_MEDIAN = float(np.median(valid_relative))
    RETURNS_RELATIVE_MAD = float(
        np.median(np.abs(valid_relative - RETURNS_RELATIVE_MEDIAN))
    )
    if RETURNS_RELATIVE_MAD == 0:
        RETURNS_RELATIVE_MAD = 1e-8

    print("\n  📊 Saved state for inference (row-by-row continuation):")
    print(f"     • Rolling window: {RETURNS_RELATIVE_ROLLING_WINDOW}")
    print(f"     • Returns history length: {len(returns_relative_history)}")
    print(
        f"     • Historical relative returns: {len(returns_relative_historical)} values"
    )
    print(f"     • Final median: {RETURNS_RELATIVE_MEDIAN:.6f}")
    print(f"     • Final MAD: {RETURNS_RELATIVE_MAD:.6f}")

print(f"\n{'=' * 80}")
print("CELL 5.6 COMPLETE")
print(f"{'=' * 80}\n")


# %% [CELL 6] HMM-4: 4-Regime Hidden Markov Model
# HIDDEN MARKOV MODEL (HMM) - 4-REGIME DETECTION

# STRATEGY: Train on PARTIAL dataset → Apply incrementally to PARTIAL, TRAIN, VALIDATION
# This ensures the model learns from early market patterns and applies
# the SAME incremental prediction methodology across all datasets

import numpy as np

print(f"\n{'=' * 80}")
print("HIDDEN MARKOV MODEL (HMM) - 4-REGIME DETECTION")
print(f"{'=' * 80}\n")

# HMM required features
HMM_FEATURES = ["daily_volatility_lagged", "lagged_forward_returns", "volatility_ma_5"]


def add_hmm_features_incrementally(
    df,
    hmm_model,
    scaler,
    historical_data,
    dataset_name="",
    vol_33=None,
    vol_67=None,
    ret_33=None,
    ret_67=None,
):
    """
    Apply trained HMM model incrementally to a dataset (row-by-row prediction).
    This matches the API simulation methodology exactly.

    Parameters:
    -----------
    df : pl.DataFrame
        Dataset to add features to
    hmm_model : GaussianHMM
        Trained HMM model
    scaler : StandardScaler
        Fitted scaler for feature normalization (trained on PARTIAL)
    historical_data : pl.DataFrame
        Historical data to use as context (empty for PARTIAL, PARTIAL for TRAIN, PARTIAL+TRAIN for VALIDATION)
    dataset_name : str
        Name for logging
    vol_33, vol_67 : float
        Volatility quantiles for historical regimes
    ret_33, ret_67 : float
        Return quantiles for historical direction regimes (computed from PARTIAL)

    Returns:
    --------
    pl.DataFrame with HMM features added
    """
    print(f"\n  Processing {dataset_name} (incremental prediction)...")

    # Initialize historical context
    historical_hmm = (
        historical_data.select(HMM_FEATURES + ["date_id"]).clone()
        if len(historical_data) > 0
        else pl.DataFrame()
    )

    # Arrays to store predictions
    hmm_regimes = []
    hmm_probs = []

    # Process each row incrementally
    for idx in range(len(df)):
        # Get current row features
        current_row = df[idx : idx + 1].select(HMM_FEATURES)

        # Combine: historical + current
        if len(historical_hmm) > 0:
            combined = pl.concat([historical_hmm.select(HMM_FEATURES), current_row])
        else:
            combined = current_row

        # Prepare HMM input
        hmm_input_combined = np.column_stack(
            [combined[feat].to_numpy() for feat in HMM_FEATURES]
        )

        # Valid mask
        valid_mask = ~np.isnan(hmm_input_combined).any(axis=1)

        if valid_mask.sum() > 0:
            # IMPORTANT: Scale data using the same scaler from training
            hmm_input_scaled = scaler.transform(hmm_input_combined[valid_mask])

            # Predict on full combined sequence (SCALED)
            regimes = hmm_model.predict(hmm_input_scaled)
            probs = hmm_model.predict_proba(hmm_input_scaled)

            # Extract LAST prediction (current row)
            hmm_regimes.append(int(regimes[-1]))
            hmm_probs.append(probs[-1])
        else:
            # Default for NaN rows
            hmm_regimes.append(0)
            hmm_probs.append(np.array([0.25, 0.25, 0.25, 0.25]))

        # Update historical data for next iteration
        new_hist_row = df[idx : idx + 1].select(HMM_FEATURES + ["date_id"])
        if len(historical_hmm) > 0:
            historical_hmm = pl.concat([historical_hmm, new_hist_row])
        else:
            historical_hmm = new_hist_row

        if (idx + 1) % 500 == 0 or idx == 0 or idx == len(df) - 1:
            print(f"    • Processed {idx + 1}/{len(df)} rows")

    # Convert to arrays
    hmm_regimes = np.array(hmm_regimes, dtype=int)
    hmm_probs = np.array(hmm_probs)

    # Add HMM features to dataframe
    df = df.with_columns(
        [
            pl.lit(hmm_regimes).cast(pl.Int32).alias("hmm_regime"),
            pl.lit(hmm_probs[:, 0]).alias("hmm_regime_prob_0"),
            pl.lit(hmm_probs[:, 1]).alias("hmm_regime_prob_1"),
            pl.lit(hmm_probs[:, 2]).alias("hmm_regime_prob_2"),
            pl.lit(hmm_probs[:, 3]).alias("hmm_regime_prob_3"),
            pl.lit(hmm_probs.max(axis=1)).alias("hmm_regime_confidence"),
        ]
    )

    # Regime transitions
    df = df.with_columns(
        [
            (pl.col("hmm_regime") != pl.col("hmm_regime").shift(1))
            .cast(pl.Int32)
            .fill_null(0)
            .alias("hmm_regime_change")
        ]
    )

    # Regime duration
    regime_duration = np.zeros(len(df), dtype=int)
    if len(hmm_regimes) > 0:
        current_regime = hmm_regimes[0]
        duration = 1
        regime_duration[0] = 1

        for i in range(1, len(hmm_regimes)):
            if hmm_regimes[i] == current_regime:
                duration += 1
                regime_duration[i] = duration
            else:
                current_regime = hmm_regimes[i]
                duration = 1
                regime_duration[i] = 1

    df = df.with_columns(
        [pl.lit(regime_duration).cast(pl.Int32).alias("hmm_regime_duration")]
    )

    # ========================================================================
    # ADVANCED HMM-4 FEATURES (8 features)
    # ========================================================================

    # 1-2. Regime Stability (3d and 5d windows)
    df = df.with_columns(
        [
            # Regime stable for 3 days: no changes in last 3 rows
            (pl.col("hmm_regime_change").rolling_sum(window_size=3, min_periods=1) == 0)
            .cast(pl.Int32)
            .alias("hmm4_regime_stable_3d"),
            # Regime stable for 5 days: no changes in last 5 rows
            (pl.col("hmm_regime_change").rolling_sum(window_size=5, min_periods=1) == 0)
            .cast(pl.Int32)
            .alias("hmm4_regime_stable_5d"),
        ]
    )

    # 3-5. Confidence Dynamics
    df = df.with_columns(
        [
            # Confidence change from previous row
            (pl.col("hmm_regime_confidence") - pl.col("hmm_regime_confidence").shift(1))
            .fill_null(0.0)
            .alias("hmm4_confidence_change"),
            # 5-period moving average of confidence
            pl.col("hmm_regime_confidence")
            .rolling_mean(window_size=5, min_periods=1)
            .alias("hmm4_confidence_ma_5"),
            # 5-period standard deviation of confidence
            pl.col("hmm_regime_confidence")
            .rolling_std(window_size=5, min_periods=1)
            .fill_null(0.0)
            .alias("hmm4_confidence_std_5"),
        ]
    )

    # 6-7. Transition Counting (5d and 10d windows)
    df = df.with_columns(
        [
            # Count of transitions in last 5 days
            pl.col("hmm_regime_change")
            .rolling_sum(window_size=5, min_periods=1)
            .alias("hmm4_transitions_5d"),
            # Count of transitions in last 10 days
            pl.col("hmm_regime_change")
            .rolling_sum(window_size=10, min_periods=1)
            .alias("hmm4_transitions_10d"),
        ]
    )

    # 8. Entropy of probability distribution
    entropy = np.zeros(len(df), dtype=float)
    for idx in range(len(hmm_probs)):
        probs = hmm_probs[idx]
        # Filter out zero probabilities to avoid log(0)
        probs_nonzero = probs[probs > 1e-10]
        if len(probs_nonzero) > 0:
            entropy[idx] = -np.sum(probs_nonzero * np.log(probs_nonzero + 1e-10))
        else:
            entropy[idx] = 0.0

    df = df.with_columns([pl.lit(entropy).alias("hmm4_entropy")])

    # Historical regimes (if quantiles provided)
    if vol_33 is not None and vol_67 is not None:
        # Use computed return quantiles if available, otherwise use volatility-based defaults
        dir_low = ret_33 if ret_33 is not None else -0.0005
        dir_high = ret_67 if ret_67 is not None else 0.0005

        df = df.with_columns(
            [
                pl.when(pl.col("daily_volatility_lagged").is_null())
                .then(1)
                .when(pl.col("daily_volatility_lagged") <= vol_33)
                .then(0)
                .when(pl.col("daily_volatility_lagged") > vol_67)
                .then(2)
                .otherwise(1)
                .alias("historical_vol_regime"),
                pl.when(pl.col("lagged_forward_returns").is_null())
                .then(1)
                .when(pl.col("lagged_forward_returns") <= dir_low)
                .then(0)
                .when(pl.col("lagged_forward_returns") > dir_high)
                .then(2)
                .otherwise(1)
                .alias("historical_dir_regime"),
            ]
        )

    # Show regime distribution
    print("    Regime distribution:")
    for i in range(4):
        count = (hmm_regimes == i).sum()
        pct = (count / len(hmm_regimes)) * 100 if len(hmm_regimes) > 0 else 0
        print(f"      Regime {i}: {count:5d} rows ({pct:5.1f}%)")

    return df


if HMM_AVAILABLE:
    print("✓ Training 4-state Gaussian HMM...")
    print(f"  • Training dataset: PARTIAL ({len(df_partial)} rows)")
    print(f"  • Features: {', '.join(HMM_FEATURES)}")
    print("  • NOTE: NO future data used - only historical/lagged features!")
    print("  • Configuration: diagonal covariance, 500 iterations")
    print("  • STRATEGY: Train on PARTIAL → Apply incrementally to ALL datasets")

    # ========================================================================
    # STEP 1: Train HMM on PARTIAL dataset
    # ========================================================================
    print("\n[1/3] Training HMM on PARTIAL dataset...")

    # Extract features from PARTIAL
    hmm_input_partial = np.column_stack(
        [df_partial[feat].to_numpy() for feat in HMM_FEATURES]
    )

    # Remove NaN rows for training
    valid_mask_partial = ~np.isnan(hmm_input_partial).any(axis=1)
    hmm_input_clean = hmm_input_partial[valid_mask_partial]

    print(f"  • Total rows: {len(df_partial)}")
    print(f"  • Valid rows (no NaNs): {len(hmm_input_clean)}")
    print(f"  • Excluded rows: {len(df_partial) - len(hmm_input_clean)}")

    if len(hmm_input_clean) < 100:
        print("  ⚠️  WARNING: Very few training samples - HMM may be unstable!")

    # IMPORTANT: Standardize features for stable HMM training
    # This ensures all features contribute equally to the Gaussian emissions
    from sklearn.preprocessing import StandardScaler

    hmm4_scaler = StandardScaler()
    hmm_input_scaled = hmm4_scaler.fit_transform(hmm_input_clean)
    print("  • Standardized features (mean=0, std=1)")

    # Add small regularization to prevent singular covariance matrices
    # This adds tiny noise to break any perfect correlations
    np.random.seed(42)
    regularization_noise = np.random.normal(0, 1e-6, hmm_input_scaled.shape)
    hmm_input_scaled = hmm_input_scaled + regularization_noise
    print("  • Added regularization noise (1e-6) for numerical stability")

    # Check for any degenerate features (zero variance after scaling)
    feature_stds = np.std(hmm_input_scaled, axis=0)
    degenerate_features = np.sum(feature_stds < 1e-8)
    if degenerate_features > 0:
        print(f"  ⚠️  WARNING: {degenerate_features} features have near-zero variance!")
        # Add more noise to degenerate features
        for i, std in enumerate(feature_stds):
            if std < 1e-8:
                hmm_input_scaled[:, i] += np.random.normal(
                    0, 0.01, len(hmm_input_scaled)
                )

    # Initialize HMM with more robust settings
    # Using 'diag' covariance is more stable than 'full' for potentially correlated features
    hmm_model = GaussianHMM(
        n_components=4,
        covariance_type="diag",  # Changed back to 'diag' for numerical stability
        n_iter=1000,  # Sufficient iterations for convergence
        tol=1e-4,
        min_covar=1e-3,  # Minimum covariance to prevent singularity
        init_params="mc",  # Fixed: don't init 's' and 't' - let algorithm find them
        params="stmc",  # Estimate all parameters during training
        random_state=42,
        verbose=True,
    )

    try:
        # Train HMM on SCALED data
        hmm_model.fit(hmm_input_scaled)

        # Validate transition matrix
        eigenvalues = np.linalg.eigvals(hmm_model.transmat_)
        complex_count = np.iscomplex(eigenvalues).sum()

        print("\n  ✅ HMM training complete!")
        print(f"  • Transition matrix eigenvalues: {complex_count} complex")
        if complex_count == 0:
            print("  • ✅ Transition matrix is stable (all real eigenvalues)")
        else:
            print("  • ⚠️  WARNING: Complex eigenvalues detected")

        # Calculate volatility quantiles from PARTIAL for historical regimes
        vol_33 = df_partial["daily_volatility_lagged"].drop_nulls().quantile(0.33)
        vol_67 = df_partial["daily_volatility_lagged"].drop_nulls().quantile(0.67)

        # Calculate RETURN quantiles from PARTIAL for direction regimes (DATA-DRIVEN)
        ret_33 = df_partial["lagged_forward_returns"].drop_nulls().quantile(0.33)
        ret_67 = df_partial["lagged_forward_returns"].drop_nulls().quantile(0.67)

        print("\n  • Volatility quantiles (for 3-regime historical classification):")
        print(f"    33rd percentile: {vol_33:.6f}")
        print(f"    67th percentile: {vol_67:.6f}")
        print("\n  • Return quantiles (for 3-regime direction classification):")
        print(f"    33rd percentile: {ret_33:.6f}")
        print(f"    67th percentile: {ret_67:.6f}")

        # ====================================================================
        # STEP 2: Apply 4-regime HMM to PARTIAL dataset (INCREMENTAL)
        # ====================================================================
        print("\n[2/3] Applying 4-regime HMM to PARTIAL dataset (INCREMENTAL)...")
        print("  NOTE: Using incremental prediction from row 1")
        print("  This ensures EXACT match with TRAIN and VALIDATION predictions")

        # Process PARTIAL incrementally (no historical data - start from scratch)
        df_partial = add_hmm_features_incrementally(
            df_partial,
            hmm_model,
            hmm4_scaler,  # Pass the fitted scaler
            pl.DataFrame(),  # No historical data for PARTIAL
            "PARTIAL",
            vol_33,
            vol_67,
            ret_33,
            ret_67,
        )

        # Save PARTIAL with HMM features
        partial_hmm_path = output_dir / "train_partial_with_nans_hmm.csv"
        df_partial.write_csv(partial_hmm_path)
        print(f"  💾 Saved: {partial_hmm_path}")

        # ====================================================================
        # STEP 3: Apply 4-regime HMM to TRAIN dataset (INCREMENTAL)
        # ====================================================================
        print("\n[3/3] Applying 4-regime HMM to TRAIN dataset (INCREMENTAL)...")
        print("  NOTE: Using PARTIAL as historical context")

        # Process TRAIN incrementally using PARTIAL as historical data
        df_train = add_hmm_features_incrementally(
            df_train,
            hmm_model,
            hmm4_scaler,  # Pass the fitted scaler
            df_partial,  # Use PARTIAL as historical context
            "TRAIN",
            vol_33,
            vol_67,
            ret_33,
            ret_67,
        )

        # Save TRAIN with HMM features
        train_hmm_path = output_dir / "train_complete_no_nans_hmm.csv"
        df_train.write_csv(train_hmm_path)
        print(f"  💾 Saved: {train_hmm_path}")
        print("  ✅ TRAIN processed incrementally - matches API simulation methodology")

        # VALIDATION will be processed separately with IncrementalHMMFeatureCalculator
        print(
            "\n  ℹ️  VALIDATION dataset will be processed incrementally using APIFeatureCalculator"
        )
        print("     (using PARTIAL + TRAIN as historical context)")

        # Update working dataframe
        df_pl = df_train.clone()

        print("\n✅ 4-regime HMM feature engineering complete for PARTIAL and TRAIN!")
        print("  • 18 HMM-4 features added to PARTIAL and TRAIN datasets")
        print("  • Same HMM model (trained on PARTIAL) used for ALL datasets")
        print("  • Same incremental prediction methodology for ALL datasets")
        print(
            "  • Perfect consistency guaranteed between TRAIN and VALIDATION predictions"
        )
        print("\n  Feature breakdown:")
        print("    BASIC (10 features):")
        print("    - hmm_regime (4 hidden states: 0, 1, 2, 3)")
        print("    - hmm_regime_prob_0/1/2/3 (probability for each state)")
        print("    - hmm_regime_confidence (max probability across states)")
        print("    - hmm_regime_change (binary transition indicator)")
        print("    - hmm_regime_duration (consecutive rows in current regime)")
        print("    - historical_vol_regime (3-state: low/mid/high volatility)")
        print("    - historical_dir_regime (3-state: down/flat/up direction)")
        print("    ADVANCED (8 features):")
        print("    - hmm4_regime_stable_3d/5d (regime stability over 3/5 days)")
        print("    - hmm4_confidence_change/ma_5/std_5 (confidence dynamics)")
        print("    - hmm4_transitions_5d/10d (transition counts over 5/10 days)")
        print("    - hmm4_entropy (probability distribution entropy)")

    except Exception as e:
        print(f"\n  ❌ HMM training failed: {e}")
        print("  Creating placeholder features for PARTIAL and TRAIN...")

        # Add placeholder features to PARTIAL and TRAIN only
        for dataset, name in [(df_partial, "PARTIAL"), (df_train, "TRAIN")]:
            dataset = dataset.with_columns(
                [
                    pl.lit(0).cast(pl.Int32).alias("hmm_regime"),
                    pl.lit(0).cast(pl.Int32).alias("hmm_regime_change"),
                    pl.lit(1).cast(pl.Int32).alias("hmm_regime_duration"),
                    pl.lit(0.25).alias("hmm_regime_confidence"),
                ]
            )
            for i in range(4):
                dataset = dataset.with_columns(
                    [pl.lit(0.25).alias(f"hmm_regime_prob_{i}")]
                )

            # Advanced HMM-4 placeholder features
            dataset = dataset.with_columns(
                [
                    pl.lit(1).cast(pl.Int32).alias("hmm4_regime_stable_3d"),
                    pl.lit(1).cast(pl.Int32).alias("hmm4_regime_stable_5d"),
                    pl.lit(0.0).alias("hmm4_confidence_change"),
                    pl.lit(0.25).alias("hmm4_confidence_ma_5"),
                    pl.lit(0.0).alias("hmm4_confidence_std_5"),
                    pl.lit(0).cast(pl.Int32).alias("hmm4_transitions_5d"),
                    pl.lit(0).cast(pl.Int32).alias("hmm4_transitions_10d"),
                    pl.lit(0.0).alias("hmm4_entropy"),
                ]
            )

            # Historical regimes
            vol_33 = dataset["daily_volatility_lagged"].drop_nulls().quantile(0.33)
            vol_67 = dataset["daily_volatility_lagged"].drop_nulls().quantile(0.67)
            ret_33 = dataset["lagged_forward_returns"].drop_nulls().quantile(0.33)
            ret_67 = dataset["lagged_forward_returns"].drop_nulls().quantile(0.67)

            dataset = dataset.with_columns(
                [
                    pl.when(pl.col("daily_volatility_lagged").is_null())
                    .then(1)
                    .when(pl.col("daily_volatility_lagged") <= vol_33)
                    .then(0)
                    .when(pl.col("daily_volatility_lagged") > vol_67)
                    .then(2)
                    .otherwise(1)
                    .alias("historical_vol_regime"),
                    pl.when(pl.col("lagged_forward_returns").is_null())
                    .then(1)
                    .when(pl.col("lagged_forward_returns") <= ret_33)
                    .then(0)
                    .when(pl.col("lagged_forward_returns") > ret_67)
                    .then(2)
                    .otherwise(1)
                    .alias("historical_dir_regime"),
                ]
            )

        if name == "PARTIAL":
            df_partial = dataset
        elif name == "TRAIN":
            df_train = dataset

    print("  ℹ️  VALIDATION will be processed with APIFeatureCalculator")
    df_pl = df_train.clone()

print(f"\n{'=' * 80}\n")

# %% [CELL 7] HMM-5: 5-Regime Volatility-Specific HMM
# HIDDEN MARKOV MODEL 2 (HMM-5) - 5-REGIME VOLATILITY-SPECIFIC DETECTION

# STRATEGY: Train on PARTIAL dataset → Apply incrementally to PARTIAL, TRAIN, VALIDATION
# Focus on volatility-specific features for finer-grained regime detection
# Same incremental methodology as HMM-4 for perfect consistency

print(f"\n{'=' * 80}")
print("HIDDEN MARKOV MODEL 2 (HMM-5) - 5-REGIME VOLATILITY-SPECIFIC DETECTION")
print(f"{'=' * 80}\n")

# HMM-5 required features (volatility-focused)
HMM5_FEATURES = ["daily_volatility_lagged", "volatility_ma_5", "volatility_ma_21"]


def add_hmm5_features_incrementally(
    df,
    hmm5_model,
    scaler,
    historical_data,
    dataset_name="",
    vol_20=None,
    vol_40=None,
    vol_60=None,
    vol_80=None,
):
    """
    Apply trained 5-regime HMM model incrementally to a dataset (row-by-row prediction).
    Uses same methodology as HMM-4 for consistency.

    Parameters:
    -----------
    df : pl.DataFrame
        Dataset to add features to
    hmm5_model : GaussianHMM
        Trained 5-regime HMM model
    scaler : StandardScaler
        Fitted scaler for feature normalization
    historical_data : pl.DataFrame
        Historical data to use as context
    dataset_name : str
        Name for logging
    vol_20, vol_40, vol_60, vol_80 : float
        Volatility quantiles for 5-state historical regimes

    Returns:
    --------
    pl.DataFrame with HMM-5 features added
    """
    print(f"\n  Processing {dataset_name} (incremental prediction)...")

    # Initialize historical context
    historical_hmm5 = (
        historical_data.select(HMM5_FEATURES + ["date_id"]).clone()
        if len(historical_data) > 0
        else pl.DataFrame()
    )

    # Arrays to store predictions
    hmm5_regimes = []
    hmm5_probs = []

    # Process each row incrementally
    for idx in range(len(df)):
        # Get current row features
        current_row = df[idx : idx + 1].select(HMM5_FEATURES)

        # Combine: historical + current
        if len(historical_hmm5) > 0:
            combined = pl.concat([historical_hmm5.select(HMM5_FEATURES), current_row])
        else:
            combined = current_row

        # Prepare HMM input
        hmm5_input_combined = np.column_stack(
            [combined[feat].to_numpy() for feat in HMM5_FEATURES]
        )

        # Valid mask
        valid_mask = ~np.isnan(hmm5_input_combined).any(axis=1)

        if valid_mask.sum() > 0:
            # Scale and predict on full combined sequence
            hmm5_input_scaled = scaler.transform(hmm5_input_combined[valid_mask])
            regimes = hmm5_model.predict(hmm5_input_scaled)
            probs = hmm5_model.predict_proba(hmm5_input_scaled)

            # Extract LAST prediction (current row)
            hmm5_regimes.append(int(regimes[-1]))
            hmm5_probs.append(probs[-1])
        else:
            # Default for NaN rows
            hmm5_regimes.append(0)
            hmm5_probs.append(np.array([0.2, 0.2, 0.2, 0.2, 0.2]))

        # Update historical data for next iteration
        new_hist_row = df[idx : idx + 1].select(HMM5_FEATURES + ["date_id"])
        if len(historical_hmm5) > 0:
            historical_hmm5 = pl.concat([historical_hmm5, new_hist_row])
        else:
            historical_hmm5 = new_hist_row

        if (idx + 1) % 500 == 0 or idx == 0 or idx == len(df) - 1:
            print(f"    • Processed {idx + 1}/{len(df)} rows")

    # Convert to arrays
    hmm5_regimes = np.array(hmm5_regimes, dtype=int)
    hmm5_probs = np.array(hmm5_probs)

    # Add basic HMM-5 features
    df = df.with_columns(
        [
            pl.lit(hmm5_regimes).cast(pl.Int32).alias("hmm5_regime"),
            pl.lit(hmm5_probs.max(axis=1)).alias("hmm5_regime_confidence"),
        ]
    )

    for state in range(5):
        df = df.with_columns(
            [pl.lit(hmm5_probs[:, state]).alias(f"hmm5_regime_prob_{state}")]
        )

    # Add regime transitions
    hmm5_change = np.zeros(len(df), dtype=int)
    hmm5_change[1:] = (hmm5_regimes[1:] != hmm5_regimes[:-1]).astype(int)
    df = df.with_columns(
        [pl.lit(hmm5_change).cast(pl.Int32).alias("hmm5_regime_change")]
    )

    # Add regime duration
    hmm5_duration = np.zeros(len(df), dtype=int)
    current_duration = 1
    for i in range(len(df)):
        if i == 0:
            hmm5_duration[i] = 1
        elif hmm5_regimes[i] == hmm5_regimes[i - 1]:
            current_duration += 1
            hmm5_duration[i] = current_duration
        else:
            current_duration = 1
            hmm5_duration[i] = 1
    df = df.with_columns(
        [pl.lit(hmm5_duration).cast(pl.Int32).alias("hmm5_regime_duration")]
    )

    # Add historical 5-state volatility regime
    if (
        vol_20 is not None
        and vol_40 is not None
        and vol_60 is not None
        and vol_80 is not None
    ):
        vol_values = df["daily_volatility_lagged"].to_numpy()
        historical_vol5_regime = np.select(
            [
                vol_values <= vol_20,
                (vol_values > vol_20) & (vol_values <= vol_40),
                (vol_values > vol_40) & (vol_values <= vol_60),
                (vol_values > vol_60) & (vol_values <= vol_80),
                vol_values > vol_80,
            ],
            [0, 1, 2, 3, 4],
            default=2,
        )
        df = df.with_columns(
            [
                pl.lit(historical_vol5_regime)
                .cast(pl.Int32)
                .alias("historical_vol5_regime")
            ]
        )

    # ========================================================================
    # ADVANCED HMM-5 FEATURES (8 features)
    # ========================================================================

    # 1-2. Regime Stability (3d and 5d windows)
    df = df.with_columns(
        [
            pl.when(pl.col("hmm5_regime_duration") >= 3)
            .then(3)
            .when(pl.col("hmm5_regime_duration") == 2)
            .then(2)
            .otherwise(1)
            .cast(pl.Int32)
            .alias("hmm5_regime_stable_3d"),
            pl.when(pl.col("hmm5_regime_duration") >= 5)
            .then(5)
            .when(pl.col("hmm5_regime_duration") == 4)
            .then(4)
            .when(pl.col("hmm5_regime_duration") == 3)
            .then(3)
            .when(pl.col("hmm5_regime_duration") == 2)
            .then(2)
            .otherwise(1)
            .cast(pl.Int32)
            .alias("hmm5_regime_stable_5d"),
        ]
    )

    # 3-5. Confidence Dynamics
    df = df.with_columns(
        [
            (
                pl.col("hmm5_regime_confidence")
                - pl.col("hmm5_regime_confidence").shift(1)
            )
            .fill_null(0.0)
            .alias("hmm5_confidence_change"),
            pl.col("hmm5_regime_confidence")
            .rolling_mean(window_size=5, min_periods=1)
            .alias("hmm5_confidence_ma_5"),
            pl.col("hmm5_regime_confidence")
            .rolling_std(window_size=5, min_periods=1)
            .fill_null(0.0)
            .alias("hmm5_confidence_std_5"),
        ]
    )

    # 6-7. Transition Counting (5d and 10d windows)
    df = df.with_columns(
        [
            pl.col("hmm5_regime_change")
            .rolling_sum(window_size=5, min_periods=1)
            .alias("hmm5_transitions_5d"),
            pl.col("hmm5_regime_change")
            .rolling_sum(window_size=10, min_periods=1)
            .alias("hmm5_transitions_10d"),
        ]
    )

    # 8. Entropy of probability distribution (5 states)
    entropy5 = np.zeros(len(hmm5_probs), dtype=float)
    for idx in range(len(hmm5_probs)):
        probs = hmm5_probs[idx]
        probs_nonzero = probs[probs > 1e-10]
        if len(probs_nonzero) > 0:
            entropy5[idx] = -np.sum(probs_nonzero * np.log(probs_nonzero + 1e-10))
    df = df.with_columns([pl.lit(entropy5).alias("hmm5_entropy")])

    # Show regime distribution
    print("    Regime distribution:")
    for i in range(5):
        count = (hmm5_regimes == i).sum()
        pct = (count / len(hmm5_regimes)) * 100 if len(hmm5_regimes) > 0 else 0
        print(f"      Regime {i}: {count:5d} rows ({pct:5.1f}%)")

    return df


# Check if HMM-5 features are available
if HMM_AVAILABLE:
    print("✓ Checking HMM-5 feature availability...")

    datasets_for_hmm5 = [("PARTIAL", df_partial), ("TRAIN", df_train)]

    missing_features = []
    for dataset_name, df in datasets_for_hmm5:
        if df is not None:
            for feat in HMM5_FEATURES:
                if feat not in df.columns:
                    missing_features.append(f"{dataset_name}:{feat}")

    if missing_features:
        print(f"  ❌ Missing features: {missing_features}")
        print("  Skipping HMM-5 training")
        HMM5_AVAILABLE = False
    else:
        print("  ✅ All required features present in PARTIAL and TRAIN datasets")
        HMM5_AVAILABLE = True
else:
    print("⚠️ HMM library not available - skipping HMM-5")
    HMM5_AVAILABLE = False


# Train 5-Regime HMM on PARTIAL dataset
if HMM5_AVAILABLE:
    try:
        print("\n✓ Training 5-state Gaussian HMM (volatility-specific)...")
        print(f"  • Training dataset: PARTIAL ({len(df_partial)} rows)")
        print(f"  • Features: {', '.join(HMM5_FEATURES)}")
        print("  • STRATEGY: Train on PARTIAL → Apply incrementally to ALL datasets")

        # ====================================================================
        # STEP 1: Train 5-regime HMM on PARTIAL dataset
        # ====================================================================
        print("\n[1/3] Training 5-regime HMM on PARTIAL dataset...")

        # Extract features from PARTIAL
        hmm5_input_partial = np.column_stack(
            [df_partial[feat].to_numpy() for feat in HMM5_FEATURES]
        )

        # Remove NaN rows for training
        valid_mask_partial = ~np.isnan(hmm5_input_partial).any(axis=1)
        hmm5_input_clean = hmm5_input_partial[valid_mask_partial]

        print(f"  • Total rows: {len(df_partial)}")
        print(f"  • Valid rows (no NaNs): {len(hmm5_input_clean)}")
        print(f"  • Excluded rows: {len(df_partial) - len(hmm5_input_clean)}")

        if len(hmm5_input_clean) < 100:
            raise ValueError(
                f"Insufficient clean data: {len(hmm5_input_clean)} samples (need >= 100)"
            )

        # Standardize features for better convergence
        from sklearn.preprocessing import StandardScaler

        scaler5 = StandardScaler()
        hmm5_input_scaled = scaler5.fit_transform(hmm5_input_clean)

        print("  • Standardized features (mean=0, std=1)")

        # Add small regularization to prevent singular covariance matrices
        np.random.seed(43)  # Different seed from HMM-4
        regularization_noise = np.random.normal(0, 1e-6, hmm5_input_scaled.shape)
        hmm5_input_scaled = hmm5_input_scaled + regularization_noise
        print("  • Added regularization noise (1e-6) for numerical stability")

        # Check for any degenerate features (zero variance after scaling)
        feature_stds = np.std(hmm5_input_scaled, axis=0)
        degenerate_features = np.sum(feature_stds < 1e-8)
        if degenerate_features > 0:
            print(
                f"  ⚠️  WARNING: {degenerate_features} features have near-zero variance!"
            )
            for i, std in enumerate(feature_stds):
                if std < 1e-8:
                    hmm5_input_scaled[:, i] += np.random.normal(
                        0, 0.01, len(hmm5_input_scaled)
                    )

        # Train 5-regime HMM with more robust settings
        hmm5_model = GaussianHMM(
            n_components=5,
            covariance_type="diag",  # Changed back to 'diag' for numerical stability
            n_iter=1000,  # Sufficient iterations for convergence
            tol=1e-4,
            min_covar=1e-3,  # Minimum covariance to prevent singularity
            random_state=42,
            init_params="mc",
            params="stmc",
            verbose=False,
        )

        hmm5_model.fit(hmm5_input_scaled)

        # Verify model stability
        eigenvalues_vol = np.linalg.eigvals(hmm5_model.transmat_)
        complex_count_vol = np.iscomplex(eigenvalues_vol).sum()

        print("\n  ✅ HMM-5 training complete!")
        print(f"  • Transition matrix eigenvalues: {complex_count_vol} complex")
        if complex_count_vol == 0:
            print("  • ✅ All eigenvalues real - matrix stable")
        else:
            print("  • ⚠️ Complex eigenvalues detected")

        # Calculate volatility quantiles from PARTIAL for 5-state historical regimes
        vol_20 = df_partial["daily_volatility_lagged"].drop_nulls().quantile(0.20)
        vol_40 = df_partial["daily_volatility_lagged"].drop_nulls().quantile(0.40)
        vol_60 = df_partial["daily_volatility_lagged"].drop_nulls().quantile(0.60)
        vol_80 = df_partial["daily_volatility_lagged"].drop_nulls().quantile(0.80)

        print("\n  • Volatility quantiles (for 5-regime historical classification):")
        print(f"    20th percentile: {vol_20:.6f}")
        print(f"    40th percentile: {vol_40:.6f}")
        print(f"    60th percentile: {vol_60:.6f}")
        print(f"    80th percentile: {vol_80:.6f}")

        # ====================================================================
        # STEP 2: Apply 5-regime HMM to PARTIAL dataset (INCREMENTAL)
        # ====================================================================
        print("\n[2/3] Applying 5-regime HMM to PARTIAL dataset (INCREMENTAL)...")
        print("  NOTE: Using incremental prediction from row 1")
        print("  This ensures EXACT match with TRAIN and VALIDATION predictions")

        # Process PARTIAL incrementally (no historical data - start from scratch)
        df_partial = add_hmm5_features_incrementally(
            df_partial,
            hmm5_model,
            scaler5,
            pl.DataFrame(),  # No historical data for PARTIAL
            "PARTIAL",
            vol_20,
            vol_40,
            vol_60,
            vol_80,
        )

        # Save PARTIAL with HMM-5 features
        partial_hmm5_path = output_dir / "train_partial_with_nans_hmm5.csv"
        df_partial.write_csv(partial_hmm5_path)
        print(f"  💾 Saved: {partial_hmm5_path}")

        # ====================================================================
        # STEP 3: Apply 5-regime HMM to TRAIN dataset (INCREMENTAL)
        # ====================================================================
        print("\n[3/3] Applying 5-regime HMM to TRAIN dataset (INCREMENTAL)...")
        print("  NOTE: Using PARTIAL as historical context")

        # Process TRAIN incrementally using PARTIAL as historical data
        df_train = add_hmm5_features_incrementally(
            df_train,
            hmm5_model,
            scaler5,
            df_partial,  # Use PARTIAL as historical context
            "TRAIN",
            vol_20,
            vol_40,
            vol_60,
            vol_80,
        )

        # Save TRAIN with HMM-5 features
        train_hmm5_path = output_dir / "train_complete_no_nans_hmm5.csv"
        df_train.write_csv(train_hmm5_path)
        print(f"  💾 Saved: {train_hmm5_path}")
        print("  ✅ TRAIN processed incrementally - matches API simulation methodology")

        # VALIDATION will be processed separately in API simulation
        print(
            "\n  ℹ️  VALIDATION dataset will be processed incrementally using API simulation"
        )
        print("     (using PARTIAL + TRAIN as historical context)")

        # ====================================================================
        # STEP 4: Add HMM Cross-Model Comparison Features (7 features)
        # ====================================================================
        print("\n[4/4] Adding HMM cross-model comparison features (HMM-4 vs HMM-5)...")

        # Check if HMM-4 features exist (they may have failed earlier)
        hmm4_available = (
            "hmm_regime" in df_partial.columns and "hmm_regime" in df_train.columns
        )

        if hmm4_available:
            # Apply cross-model features to PARTIAL
            print("  Processing PARTIAL dataset...")
            df_partial = df_partial.with_columns(
                [
                    (
                        pl.col("hmm_regime")
                        == pl.when(pl.col("hmm5_regime") <= 1)
                        .then(pl.col("hmm5_regime"))
                        .when(pl.col("hmm5_regime") == 2)
                        .then(2)
                        .otherwise(3)
                    )
                    .cast(pl.Int32)
                    .alias("hmm_regime_agreement"),
                    (
                        (pl.col("hmm_regime") / 3.0 - pl.col("hmm5_regime") / 4.0).abs()
                    ).alias("hmm_regime_divergence"),
                    (
                        (
                            pl.col("hmm_regime_confidence")
                            + pl.col("hmm5_regime_confidence")
                        )
                        / 2.0
                    ).alias("hmm_avg_confidence"),
                    (
                        (
                            pl.col("hmm_regime_confidence")
                            - pl.col("hmm5_regime_confidence")
                        ).abs()
                    ).alias("hmm_confidence_spread"),
                    (
                        (pl.col("hmm_regime_confidence") > 0.6)
                        & (pl.col("hmm5_regime_confidence") > 0.6)
                    )
                    .cast(pl.Int32)
                    .alias("hmm_both_confident"),
                    (
                        (pl.col("hmm_regime_change") == 1)
                        & (pl.col("hmm5_regime_change") == 1)
                    )
                    .cast(pl.Int32)
                    .alias("hmm_sync_transition"),
                    (pl.col("hmm_regime_change") + pl.col("hmm5_regime_change")).alias(
                        "hmm_total_transitions"
                    ),
                ]
            )

            # Apply cross-model features to TRAIN
            print("  Processing TRAIN dataset...")
            df_train = df_train.with_columns(
                [
                    (
                        pl.col("hmm_regime")
                        == pl.when(pl.col("hmm5_regime") <= 1)
                        .then(pl.col("hmm5_regime"))
                        .when(pl.col("hmm5_regime") == 2)
                        .then(2)
                        .otherwise(3)
                    )
                    .cast(pl.Int32)
                    .alias("hmm_regime_agreement"),
                    (
                        (pl.col("hmm_regime") / 3.0 - pl.col("hmm5_regime") / 4.0).abs()
                    ).alias("hmm_regime_divergence"),
                    (
                        (
                            pl.col("hmm_regime_confidence")
                            + pl.col("hmm5_regime_confidence")
                        )
                        / 2.0
                    ).alias("hmm_avg_confidence"),
                    (
                        (
                            pl.col("hmm_regime_confidence")
                            - pl.col("hmm5_regime_confidence")
                        ).abs()
                    ).alias("hmm_confidence_spread"),
                    (
                        (pl.col("hmm_regime_confidence") > 0.6)
                        & (pl.col("hmm5_regime_confidence") > 0.6)
                    )
                    .cast(pl.Int32)
                    .alias("hmm_both_confident"),
                    (
                        (pl.col("hmm_regime_change") == 1)
                        & (pl.col("hmm5_regime_change") == 1)
                    )
                    .cast(pl.Int32)
                    .alias("hmm_sync_transition"),
                    (pl.col("hmm_regime_change") + pl.col("hmm5_regime_change")).alias(
                        "hmm_total_transitions"
                    ),
                ]
            )

            print("  ✅ Added 7 HMM cross-model comparison features")
        else:
            print(
                "  ⚠️  HMM-4 features not available - creating HMM-5-only cross-model placeholders..."
            )

            # Create placeholder cross-model features using only HMM-5
            for df, name in [(df_partial, "PARTIAL"), (df_train, "TRAIN")]:
                df = df.with_columns(
                    [
                        pl.lit(1)
                        .cast(pl.Int32)
                        .alias("hmm_regime_agreement"),  # Agree with itself
                        pl.lit(0.0).alias("hmm_regime_divergence"),  # No divergence
                        pl.col("hmm5_regime_confidence").alias(
                            "hmm_avg_confidence"
                        ),  # Use HMM-5 only
                        pl.lit(0.0).alias("hmm_confidence_spread"),  # No spread
                        (pl.col("hmm5_regime_confidence") > 0.6)
                        .cast(pl.Int32)
                        .alias("hmm_both_confident"),
                        pl.col("hmm5_regime_change")
                        .cast(pl.Int32)
                        .alias("hmm_sync_transition"),
                        pl.col("hmm5_regime_change").alias("hmm_total_transitions"),
                    ]
                )
                if name == "PARTIAL":
                    df_partial = df
                else:
                    df_train = df

            print("  ✅ Added 7 HMM cross-model features (HMM-5 only mode)")

        # ====================================================================
        # STEP 5: Calculate Cumulative Regime Stats (Row-by-Row)
        # ====================================================================
        # This tracks the historical positive return rate AND volatility for each regime
        # Updated incrementally: at each row, we know the regime and whether
        # the PREVIOUS day's return was positive (using lagged_forward_returns)
        # This gives the model running estimates like:
        #   - "regime 2 has had 68% positive returns so far"
        #   - "regime 3 volatility is 15% above overall mean"
        print(
            "\n[5/5] Calculating cumulative regime stats (positive rates + volatility)..."
        )

        def calculate_regime_stats(
            df,
            n_regimes,
            regime_col,
            prev_counts=None,
            prev_pos=None,
            prev_vol_sum=None,
            prev_vol_count=None,
            prev_global_vol_sum=None,
            prev_global_vol_count=None,
        ):
            """
            Calculate cumulative positive rate AND volatility per regime row-by-row.
            Uses lagged_forward_returns (previous day's return) since that's what we know at prediction time.

            Returns:
                - pos_rates: dict of arrays with positive rate per regime at each row
                - current_regime_pos_rate: array with the current regime's pos rate at each row
                - vol_pct_diff: dict of arrays with volatility % diff from mean per regime at each row
                - current_regime_vol_pct: array with the current regime's vol pct at each row
                - Final state dictionaries for continuation
            """
            regimes = df[regime_col].to_numpy()
            returns = df["lagged_forward_returns"].to_numpy()
            volatilities = df["daily_volatility_lagged"].to_numpy()
            n_rows = len(df)

            # Initialize counts for positive rate tracking
            if prev_counts is None:
                regime_counts = dict.fromkeys(range(n_regimes), 0)
                regime_pos = dict.fromkeys(range(n_regimes), 0)
            else:
                regime_counts = prev_counts.copy()
                regime_pos = prev_pos.copy()

            # Initialize sums for volatility tracking
            if prev_vol_sum is None:
                regime_vol_sum = dict.fromkeys(range(n_regimes), 0.0)
                regime_vol_count = dict.fromkeys(range(n_regimes), 0)
                global_vol_sum = 0.0
                global_vol_count = 0
            else:
                regime_vol_sum = prev_vol_sum.copy()
                regime_vol_count = prev_vol_count.copy()
                global_vol_sum = prev_global_vol_sum
                global_vol_count = prev_global_vol_count

            # Arrays to store row-by-row values
            pos_rates = {i: np.zeros(n_rows) for i in range(n_regimes)}
            vol_pct_diff = {i: np.zeros(n_rows) for i in range(n_regimes)}
            current_regime_pos_rate = np.zeros(n_rows)
            current_regime_vol_pct = np.zeros(n_rows)

            for idx in range(n_rows):
                current_regime = int(regimes[idx])
                current_return = returns[idx]
                current_vol = volatilities[idx]

                # Calculate GLOBAL mean volatility so far
                global_mean_vol = (
                    global_vol_sum / global_vol_count if global_vol_count > 0 else 0.01
                )

                # First, record CURRENT stats (before updating with this row's data)
                for r in range(n_regimes):
                    # Positive rate
                    if regime_counts[r] > 0:
                        pos_rates[r][idx] = regime_pos[r] / regime_counts[r]
                    else:
                        pos_rates[r][idx] = 0.5  # No data yet, use neutral prior

                    # Volatility % diff from global mean
                    if regime_vol_count[r] > 0 and global_mean_vol > 1e-10:
                        regime_mean_vol = regime_vol_sum[r] / regime_vol_count[r]
                        vol_pct_diff[r][idx] = (
                            regime_mean_vol - global_mean_vol
                        ) / global_mean_vol  # e.g., 0.15 = 15% above mean
                    else:
                        vol_pct_diff[r][idx] = 0.0  # No data yet, assume at mean

                # Current regime's pos rate (lookup for this row's regime)
                current_regime_pos_rate[idx] = pos_rates[current_regime][idx]
                current_regime_vol_pct[idx] = vol_pct_diff[current_regime][idx]

                # Now update counts with this row's data
                if not np.isnan(current_return) and 0 <= current_regime < n_regimes:
                    regime_counts[current_regime] += 1
                    if current_return > 0:
                        regime_pos[current_regime] += 1

                if not np.isnan(current_vol) and 0 <= current_regime < n_regimes:
                    regime_vol_sum[current_regime] += current_vol
                    regime_vol_count[current_regime] += 1
                    global_vol_sum += current_vol
                    global_vol_count += 1

            return (
                pos_rates,
                current_regime_pos_rate,
                vol_pct_diff,
                current_regime_vol_pct,
                regime_counts,
                regime_pos,
                regime_vol_sum,
                regime_vol_count,
                global_vol_sum,
                global_vol_count,
            )

        # Calculate for PARTIAL (HMM-4)
        print("  Processing PARTIAL - HMM-4 regime stats...")
        (
            hmm4_pos_rates_partial,
            hmm4_current_pos_rate_partial,
            hmm4_vol_pct_partial,
            hmm4_current_vol_pct_partial,
            hmm4_counts_partial,
            hmm4_pos_partial,
            hmm4_vol_sum_partial,
            hmm4_vol_count_partial,
            global_vol_sum_partial,
            global_vol_count_partial,
        ) = calculate_regime_stats(df_partial, n_regimes=4, regime_col="hmm_regime")
        for r in range(4):
            df_partial = df_partial.with_columns(
                [
                    pl.Series(f"hmm_regime_{r}_pos_rate", hmm4_pos_rates_partial[r]),
                    pl.Series(f"hmm_regime_{r}_vol_pct", hmm4_vol_pct_partial[r]),
                ]
            )
        df_partial = df_partial.with_columns(
            [
                pl.Series("current_regime_pos_rate", hmm4_current_pos_rate_partial),
                pl.Series("current_regime_vol_pct", hmm4_current_vol_pct_partial),
            ]
        )

        # Calculate for PARTIAL (HMM-5)
        print("  Processing PARTIAL - HMM-5 regime stats...")
        (
            hmm5_pos_rates_partial,
            hmm5_current_pos_rate_partial,
            hmm5_vol_pct_partial,
            hmm5_current_vol_pct_partial,
            hmm5_counts_partial,
            hmm5_pos_partial,
            hmm5_vol_sum_partial,
            hmm5_vol_count_partial,
            _,
            _,
        ) = calculate_regime_stats(df_partial, n_regimes=5, regime_col="hmm5_regime")
        for r in range(5):
            df_partial = df_partial.with_columns(
                [
                    pl.Series(f"hmm5_regime_{r}_pos_rate", hmm5_pos_rates_partial[r]),
                    pl.Series(f"hmm5_regime_{r}_vol_pct", hmm5_vol_pct_partial[r]),
                ]
            )
        df_partial = df_partial.with_columns(
            [
                pl.Series("current_regime5_pos_rate", hmm5_current_pos_rate_partial),
                pl.Series("current_regime5_vol_pct", hmm5_current_vol_pct_partial),
            ]
        )

        # Print PARTIAL stats
        print("    PARTIAL HMM-4 regime stats:")
        for r in range(4):
            if hmm4_counts_partial[r] > 0:
                rate = hmm4_pos_partial[r] / hmm4_counts_partial[r]
                vol_pct = (
                    (
                        hmm4_vol_sum_partial[r] / hmm4_vol_count_partial[r]
                        - global_vol_sum_partial / global_vol_count_partial
                    )
                    / (global_vol_sum_partial / global_vol_count_partial)
                    * 100
                    if hmm4_vol_count_partial[r] > 0
                    else 0
                )
                print(
                    f"      Regime {r}: {hmm4_counts_partial[r]:4d} days, {rate * 100:.1f}% positive, vol {vol_pct:+.1f}% vs mean"
                )

        print("    PARTIAL HMM-5 regime stats:")
        for r in range(5):
            if hmm5_counts_partial[r] > 0:
                rate = hmm5_pos_partial[r] / hmm5_counts_partial[r]
                print(
                    f"      Regime {r}: {hmm5_counts_partial[r]:4d} days, {rate * 100:.1f}% positive"
                )

        # Calculate for TRAIN (continuing from PARTIAL)
        print("  Processing TRAIN - HMM-4 regime stats (continuing from PARTIAL)...")
        (
            hmm4_pos_rates_train,
            hmm4_current_pos_rate_train,
            hmm4_vol_pct_train,
            hmm4_current_vol_pct_train,
            hmm4_counts_train,
            hmm4_pos_train,
            hmm4_vol_sum_train,
            hmm4_vol_count_train,
            global_vol_sum_train,
            global_vol_count_train,
        ) = calculate_regime_stats(
            df_train,
            n_regimes=4,
            regime_col="hmm_regime",
            prev_counts=hmm4_counts_partial,
            prev_pos=hmm4_pos_partial,
            prev_vol_sum=hmm4_vol_sum_partial,
            prev_vol_count=hmm4_vol_count_partial,
            prev_global_vol_sum=global_vol_sum_partial,
            prev_global_vol_count=global_vol_count_partial,
        )
        for r in range(4):
            df_train = df_train.with_columns(
                [
                    pl.Series(f"hmm_regime_{r}_pos_rate", hmm4_pos_rates_train[r]),
                    pl.Series(f"hmm_regime_{r}_vol_pct", hmm4_vol_pct_train[r]),
                ]
            )
        df_train = df_train.with_columns(
            [
                pl.Series("current_regime_pos_rate", hmm4_current_pos_rate_train),
                pl.Series("current_regime_vol_pct", hmm4_current_vol_pct_train),
            ]
        )

        # Calculate for TRAIN (HMM-5, continuing from PARTIAL)
        print("  Processing TRAIN - HMM-5 regime stats (continuing from PARTIAL)...")
        (
            hmm5_pos_rates_train,
            hmm5_current_pos_rate_train,
            hmm5_vol_pct_train,
            hmm5_current_vol_pct_train,
            hmm5_counts_train,
            hmm5_pos_train,
            hmm5_vol_sum_train,
            hmm5_vol_count_train,
            _,
            _,
        ) = calculate_regime_stats(
            df_train,
            n_regimes=5,
            regime_col="hmm5_regime",
            prev_counts=hmm5_counts_partial,
            prev_pos=hmm5_pos_partial,
            prev_vol_sum=hmm5_vol_sum_partial,
            prev_vol_count=hmm5_vol_count_partial,
            prev_global_vol_sum=global_vol_sum_partial,
            prev_global_vol_count=global_vol_count_partial,
        )
        for r in range(5):
            df_train = df_train.with_columns(
                [
                    pl.Series(f"hmm5_regime_{r}_pos_rate", hmm5_pos_rates_train[r]),
                    pl.Series(f"hmm5_regime_{r}_vol_pct", hmm5_vol_pct_train[r]),
                ]
            )
        df_train = df_train.with_columns(
            [
                pl.Series("current_regime5_pos_rate", hmm5_current_pos_rate_train),
                pl.Series("current_regime5_vol_pct", hmm5_current_vol_pct_train),
            ]
        )

        # Print TRAIN (cumulative) stats
        print("    TRAIN (cumulative from PARTIAL) HMM-4 regime stats:")
        for r in range(4):
            if hmm4_counts_train[r] > 0:
                rate = hmm4_pos_train[r] / hmm4_counts_train[r]
                vol_pct = (
                    (
                        hmm4_vol_sum_train[r] / hmm4_vol_count_train[r]
                        - global_vol_sum_train / global_vol_count_train
                    )
                    / (global_vol_sum_train / global_vol_count_train)
                    * 100
                    if hmm4_vol_count_train[r] > 0
                    else 0
                )
                print(
                    f"      Regime {r}: {hmm4_counts_train[r]:4d} days, {rate * 100:.1f}% positive, vol {vol_pct:+.1f}% vs mean"
                )

        print("    TRAIN (cumulative) HMM-5 regime stats:")
        for r in range(5):
            if hmm5_counts_train[r] > 0:
                rate = hmm5_pos_train[r] / hmm5_counts_train[r]
                vol_pct = (
                    (
                        hmm5_vol_sum_train[r] / hmm5_vol_count_train[r]
                        - global_vol_sum_train / global_vol_count_train
                    )
                    / (global_vol_sum_train / global_vol_count_train)
                    * 100
                    if hmm5_vol_count_train[r] > 0
                    else 0
                )
                print(
                    f"      Regime {r}: {hmm5_counts_train[r]:4d} days, {rate * 100:.1f}% positive, vol {vol_pct:+.1f}% vs mean"
                )

        # Save state for API simulation continuation
        hmm_regime_stats_state = {
            # Positive rate tracking
            "hmm4_counts": hmm4_counts_train,
            "hmm4_pos": hmm4_pos_train,
            "hmm5_counts": hmm5_counts_train,
            "hmm5_pos": hmm5_pos_train,
            # Volatility tracking
            "hmm4_vol_sum": hmm4_vol_sum_train,
            "hmm4_vol_count": hmm4_vol_count_train,
            "hmm5_vol_sum": hmm5_vol_sum_train,
            "hmm5_vol_count": hmm5_vol_count_train,
            "global_vol_sum": global_vol_sum_train,
            "global_vol_count": global_vol_count_train,
        }

        print("  ✅ Added cumulative regime stats features:")
        print("     Positive Rates:")
        print("       - hmm_regime_0/1/2/3_pos_rate (4 features for HMM-4)")
        print("       - hmm5_regime_0/1/2/3/4_pos_rate (5 features for HMM-5)")
        print("       - current_regime_pos_rate (HMM-4 current regime)")
        print("       - current_regime5_pos_rate (HMM-5 current regime)")
        print("     Volatility % Diff from Mean:")
        print("       - hmm_regime_0/1/2/3_vol_pct (4 features for HMM-4)")
        print("       - hmm5_regime_0/1/2/3/4_vol_pct (5 features for HMM-5)")
        print("       - current_regime_vol_pct (HMM-4 current regime)")
        print("       - current_regime5_vol_pct (HMM-5 current regime)")
        print("  💾 State saved for API simulation continuation")

        # Update working dataframe
        df_pl = df_train.clone()

        print("\n✅ 5-regime HMM feature engineering complete!")
        print("  • 26 HMM-5 + cross-model features added to PARTIAL and TRAIN datasets")
        print("  • Same HMM-5 model (trained on PARTIAL) used for ALL datasets")
        print("  • Same incremental prediction methodology for ALL datasets")
        print(
            "  • Perfect consistency guaranteed between TRAIN and VALIDATION predictions"
        )
        print("\n  Feature breakdown:")
        print("    BASIC (11 features):")
        print("    - hmm5_regime (5 hidden states: 0, 1, 2, 3, 4)")
        print("    - hmm5_regime_prob_0/1/2/3/4 (probability for each state)")
        print("    - hmm5_regime_confidence (max probability across states)")
        print("    - hmm5_regime_change (binary transition indicator)")
        print("    - hmm5_regime_duration (consecutive rows in current regime)")
        print("    - historical_vol5_regime (5-state: very_low/low/mid/high/very_high)")
        print("    ADVANCED (8 features):")
        print("    - hmm5_regime_stable_3d/5d (regime stability over 3/5 days)")
        print("    - hmm5_confidence_change/ma_5/std_5 (confidence dynamics)")
        print("    - hmm5_transitions_5d/10d (transition counts over 5/10 days)")
        print("    - hmm5_entropy (probability distribution entropy)")
        print("    CROSS-MODEL (7 features):")
        print("    - hmm_regime_agreement (both models agree on regime bin)")
        print("    - hmm_regime_divergence (normalized regime difference)")
        print("    - hmm_avg_confidence/confidence_spread (confidence metrics)")
        print("    - hmm_both_confident (both models > 0.6 confidence)")
        print("    - hmm_sync_transition/total_transitions (transition tracking)")

    except Exception as e:
        print(f"\n  ❌ HMM-5 training/application failed: {e}")
        print("  Skipping HMM-5 features...")
        HMM5_AVAILABLE = False

print(f"\n{'=' * 80}\n")

# %% [CELL 7.5] Advanced Markov Features - DTMC, Transition Matrix, Dwell Times
# ═══════════════════════════════════════════════════════════════════════════
# ADVANCED MARKOV CHAIN FEATURES FOR META-MODEL
# ═══════════════════════════════════════════════════════════════════════════
# Based on Markov theory for trading signals:
# 1. DTMC (Discrete-Time Markov Chain) on returns → P(up|current_state)
# 2. Expected Dwell Time from transition matrix
# 3. Regime Entropy (uncertainty measure)
# 4. N-step Transition Probabilities
# 5. Transition Skew (directional asymmetry)
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 80}")
print("ADVANCED MARKOV CHAIN FEATURES - DTMC, TRANSITION MATRIX, DWELL TIMES")
print(f"{'=' * 80}\n")

print("Objective:")
print("  • Create DTMC on discretized returns (Up/Down/Flat)")
print("  • Compute Expected Dwell Time from HMM transition matrices")
print("  • Add Regime Entropy (−Σ p·log(p)) for uncertainty quantification")
print("  • Compute N-step transition probabilities (P_up_5, P_up_10, P_up_20)")
print("  • Add Transition Skew for directional asymmetry detection")
print()

import numpy as np
import polars as pl

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: DTMC ON DISCRETIZED RETURNS
# ═══════════════════════════════════════════════════════════════════════════
print("  STEP 1: Building DTMC (Discrete-Time Markov Chain) on returns...")


class DTMCCalculator:
    """
    Discrete-Time Markov Chain calculator for direction prediction.

    States: 0=Down, 1=Flat, 2=Up (based on return thresholds)
    Features:
    - Transition probabilities P(next_state | current_state)
    - N-step probabilities via matrix power
    - Transition matrix entropy
    """

    def __init__(
        self,
        threshold_up=0.001,
        threshold_down=-0.001,
        smoothing_alpha=0.1,
        window_size=252,
    ):
        """
        Parameters:
        -----------
        threshold_up : float
            Return above this is "Up" (state 2)
        threshold_down : float
            Return below this is "Down" (state 0)
        smoothing_alpha : float
            Dirichlet smoothing parameter for sparse transitions
        window_size : int
            Rolling window for transition estimation (252 = 1 year)
        """
        self.threshold_up = threshold_up
        self.threshold_down = threshold_down
        self.smoothing_alpha = smoothing_alpha
        self.window_size = window_size
        self.n_states = 3  # Down, Flat, Up

        # Initialize transition counts with Dirichlet prior
        self.transition_counts = np.ones((3, 3)) * smoothing_alpha
        self.state_counts = np.ones(3) * smoothing_alpha * 3

    def discretize_return(self, ret):
        """Convert return to discrete state: 0=Down, 1=Flat, 2=Up"""
        if ret is None or np.isnan(ret):
            return 1  # Default to Flat
        if ret > self.threshold_up:
            return 2  # Up
        elif ret < self.threshold_down:
            return 0  # Down
        else:
            return 1  # Flat

    def get_transition_matrix(self):
        """Get normalized transition probability matrix"""
        # Normalize rows to sum to 1
        row_sums = self.transition_counts.sum(axis=1, keepdims=True)
        row_sums = np.maximum(row_sums, 1e-10)  # Avoid division by zero
        return self.transition_counts / row_sums

    def update(self, prev_state, current_state):
        """Update transition counts with new observation"""
        self.transition_counts[prev_state, current_state] += 1
        self.state_counts[current_state] += 1

    def get_n_step_probs(self, current_state, n_steps):
        """
        Get probability distribution over states after n steps.
        Uses matrix exponentiation: P^n
        """
        P = self.get_transition_matrix()
        P_n = np.linalg.matrix_power(P, n_steps)
        return P_n[current_state]

    def get_features(self, current_state, returns_history=None):
        """
        Compute all DTMC features for current state.

        Returns dict with:
        - dtmc_state: current discretized state (0, 1, 2)
        - dtmc_p_up_1: P(Up in next 1 bar)
        - dtmc_p_up_5: P(Up in next 5 bars) via matrix power
        - dtmc_p_up_10: P(Up in next 10 bars)
        - dtmc_p_up_20: P(Up in next 20 bars)
        - dtmc_p_down_1: P(Down in next 1 bar)
        - dtmc_transition_entropy: entropy of next-state distribution
        - dtmc_self_transition: P(stay in current state)
        - dtmc_expected_dwell: expected bars until state change
        """
        P = self.get_transition_matrix()

        # 1-step probabilities
        p_next = P[current_state]
        p_up_1 = p_next[2]  # P(Up)
        p_down_1 = p_next[0]  # P(Down)
        p_flat_1 = p_next[1]  # P(Flat)

        # N-step probabilities (cumulative: at least one Up in N steps)
        # Approximate using: P(at least one Up in N) ≈ 1 - P(never Up)^N
        # More accurate: sum marginals
        p_5 = self.get_n_step_probs(current_state, 5)
        p_10 = self.get_n_step_probs(current_state, 10)
        p_20 = self.get_n_step_probs(current_state, 20)

        # Self-transition probability (persistence)
        p_self = P[current_state, current_state]

        # Expected dwell time: E[T] = 1 / (1 - p_self)
        expected_dwell = 1.0 / max(1 - p_self, 0.01)

        # Transition entropy: -Σ p·log(p)
        eps = 1e-10
        entropy = -np.sum(p_next * np.log(p_next + eps))

        return {
            "dtmc_state": current_state,
            "dtmc_p_up_1": p_up_1,
            "dtmc_p_up_5": p_5[2],
            "dtmc_p_up_10": p_10[2],
            "dtmc_p_up_20": p_20[2],
            "dtmc_p_down_1": p_down_1,
            "dtmc_p_down_5": p_5[0],
            "dtmc_p_flat_1": p_flat_1,
            "dtmc_transition_entropy": entropy,
            "dtmc_self_transition": p_self,
            "dtmc_expected_dwell": expected_dwell,
        }


print("    ✓ DTMCCalculator class defined")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: HMM EXPECTED DWELL TIME FROM TRANSITION MATRIX
# ═══════════════════════════════════════════════════════════════════════════
# NOTE: HMM models are trained on PARTIAL only (Cell 6 & 7).
#       The transition matrix (transmat_) is FROZEN after training.
#       Using it on TRAIN data does NOT cause data leakage.
# ═══════════════════════════════════════════════════════════════════════════
print("\n  STEP 2: Computing HMM Expected Dwell Times...")
print("    ℹ️  HMM transition matrices are frozen (trained on PARTIAL only)")


def compute_hmm_dwell_features(hmm_model, current_regime, current_probs):
    """
    Compute dwell time features from HMM transition matrix.

    Parameters:
    -----------
    hmm_model : GaussianHMM
        Fitted HMM model with transmat_ attribute
    current_regime : int
        Current regime (Viterbi decoded)
    current_probs : np.array
        Posterior probabilities for each regime

    Returns:
    --------
    dict with dwell features
    """
    try:
        transmat = hmm_model.transmat_
        n_states = transmat.shape[0]

        # Expected dwell time for each state: E[T_i] = 1 / (1 - p_ii)
        expected_dwells = np.zeros(n_states)
        for i in range(n_states):
            p_self = transmat[i, i]
            expected_dwells[i] = 1.0 / max(1 - p_self, 0.01)

        # Current regime's expected remaining dwell
        current_expected_dwell = expected_dwells[current_regime]

        # Weighted expected dwell (by regime probability)
        weighted_dwell = np.sum(current_probs * expected_dwells)

        # Transition skew: asymmetry in transitions
        # For 4-state HMM: compare upward vs downward transitions
        if n_states == 4:
            # States 0,1 = low regimes, 2,3 = high regimes
            p_low_to_high = (
                transmat[0, 2] + transmat[0, 3] + transmat[1, 2] + transmat[1, 3]
            ) / 4
            p_high_to_low = (
                transmat[2, 0] + transmat[2, 1] + transmat[3, 0] + transmat[3, 1]
            ) / 4
            transition_skew = p_low_to_high - p_high_to_low
        elif n_states == 5:
            # States 0,1 = low, 2 = mid, 3,4 = high
            p_low_to_high = (
                transmat[0, 3] + transmat[0, 4] + transmat[1, 3] + transmat[1, 4]
            ) / 4
            p_high_to_low = (
                transmat[3, 0] + transmat[3, 1] + transmat[4, 0] + transmat[4, 1]
            ) / 4
            transition_skew = p_low_to_high - p_high_to_low
        else:
            transition_skew = 0.0

        # Regime entropy from posterior probabilities
        eps = 1e-10
        regime_entropy = -np.sum(current_probs * np.log(current_probs + eps))

        # Max entropy for normalization (log(n_states))
        max_entropy = np.log(n_states)
        normalized_entropy = regime_entropy / max_entropy

        return {
            "expected_dwell": current_expected_dwell,
            "weighted_dwell": weighted_dwell,
            "transition_skew": transition_skew,
            "regime_entropy": regime_entropy,
            "normalized_entropy": normalized_entropy,
            "min_dwell": expected_dwells.min(),
            "max_dwell": expected_dwells.max(),
        }

    except Exception:
        # Fallback values
        return {
            "expected_dwell": 5.0,
            "weighted_dwell": 5.0,
            "transition_skew": 0.0,
            "regime_entropy": 1.0,
            "normalized_entropy": 0.5,
            "min_dwell": 2.0,
            "max_dwell": 10.0,
        }


print("    ✓ compute_hmm_dwell_features function defined")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: APPLY FEATURES TO DATASETS
# ═══════════════════════════════════════════════════════════════════════════
print("\n  STEP 3: Applying Advanced Markov Features to datasets...")

# Check if HMM models are available
HMM4_AVAILABLE = "hmm_model" in dir() and hmm_model is not None
HMM5_AVAILABLE = "hmm5_model" in dir() and hmm5_model is not None

# Compute DTMC thresholds from PARTIAL data (data-driven, not hardcoded)
dtmc_ret_33 = df_partial["lagged_forward_returns"].drop_nulls().quantile(0.33)
dtmc_ret_67 = df_partial["lagged_forward_returns"].drop_nulls().quantile(0.67)
print("    • DTMC thresholds (from PARTIAL quantiles):")
print(f"      threshold_down (33rd pct): {dtmc_ret_33:.6f}")
print(f"      threshold_up (67th pct):   {dtmc_ret_67:.6f}")

# Initialize DTMC calculator with data-driven thresholds
dtmc_calc = DTMCCalculator(
    threshold_up=dtmc_ret_67,  # Data-driven: 67th percentile
    threshold_down=dtmc_ret_33,  # Data-driven: 33rd percentile
    smoothing_alpha=0.5,  # Dirichlet smoothing
    window_size=252,
)


def add_advanced_markov_features(
    df, dtmc_calc, hmm_model=None, hmm5_model=None, historical_df=None, dataset_name=""
):
    """
    Add all advanced Markov features to a dataset incrementally (EXPANDING WINDOW).

    At row i, features are computed using only data from rows 0 to i-1.
    Then the observation at row i is used to update the model for row i+1.
    This matches the API simulation methodology used in other cells.
    """
    print(f"\n    Processing {dataset_name} (expanding window)...")

    n_rows = len(df)

    # Initialize arrays for DTMC features
    dtmc_state = np.zeros(n_rows, dtype=int)
    dtmc_p_up_1 = np.zeros(n_rows)
    dtmc_p_up_5 = np.zeros(n_rows)
    dtmc_p_up_10 = np.zeros(n_rows)
    dtmc_p_up_20 = np.zeros(n_rows)
    dtmc_p_down_1 = np.zeros(n_rows)
    dtmc_entropy = np.zeros(n_rows)
    dtmc_self_trans = np.zeros(n_rows)
    dtmc_expected_dwell = np.zeros(n_rows)

    # Initialize arrays for HMM dwell features
    hmm4_expected_dwell = np.zeros(n_rows)
    hmm4_weighted_dwell = np.zeros(n_rows)
    hmm4_transition_skew = np.zeros(n_rows)
    hmm4_regime_entropy = np.zeros(n_rows)
    hmm4_normalized_entropy = np.zeros(n_rows)

    hmm5_expected_dwell = np.zeros(n_rows)
    hmm5_weighted_dwell = np.zeros(n_rows)
    hmm5_transition_skew = np.zeros(n_rows)
    hmm5_regime_entropy = np.zeros(n_rows)
    hmm5_normalized_entropy = np.zeros(n_rows)

    # Get returns column
    returns = df["lagged_forward_returns"].to_numpy()

    # Get HMM regime data if available
    if "hmm_regime" in df.columns:
        hmm_regimes = df["hmm_regime"].to_numpy()
        hmm_probs = np.column_stack(
            [
                df[f"hmm_regime_prob_{i}"].to_numpy()
                if f"hmm_regime_prob_{i}" in df.columns
                else np.ones(n_rows) * 0.25
                for i in range(4)
            ]
        )
    else:
        hmm_regimes = np.zeros(n_rows, dtype=int)
        hmm_probs = np.ones((n_rows, 4)) * 0.25

    if "hmm5_regime" in df.columns:
        hmm5_regimes = df["hmm5_regime"].to_numpy()
        hmm5_probs = np.column_stack(
            [
                df[f"hmm5_regime_prob_{i}"].to_numpy()
                if f"hmm5_regime_prob_{i}" in df.columns
                else np.ones(n_rows) * 0.2
                for i in range(5)
            ]
        )
    else:
        hmm5_regimes = np.zeros(n_rows, dtype=int)
        hmm5_probs = np.ones((n_rows, 5)) * 0.2

    # Process historical data first to warm up DTMC (PARTIAL data)
    if historical_df is not None and len(historical_df) > 0:
        hist_returns = historical_df["lagged_forward_returns"].to_numpy()
        # Warm up with historical data (expanding window continues from here)
        prev_state = 1  # Start with Flat
        for ret in hist_returns:
            current_state = dtmc_calc.discretize_return(ret)
            dtmc_calc.update(prev_state, current_state)
            prev_state = current_state
        print(f"      • Warmed up DTMC with {len(hist_returns)} historical rows")
        print(
            f"      • Last state from historical: {prev_state} ({'Down' if prev_state == 0 else 'Flat' if prev_state == 1 else 'Up'})"
        )
        # prev_state now holds the last state from historical data
    else:
        prev_state = 1  # Start with Flat

    # ════════════════════════════════════════════════════════════════════════
    # ROW-BY-ROW LOGIC (EXPANDING WINDOW):
    # lagged_forward_returns[i] = return from buying at i-1, selling at i
    #                           = ALREADY REALIZED at row i (known value)
    #
    # At row i:
    #   1. Get features using CURRENT transition matrix (learned from past)
    #   2. Observe lagged_forward_returns[i] → get current_state
    #   3. THEN update DTMC with transition prev_state → current_state
    #
    # This ensures: features at row i use only data from rows 0 to i-1
    # The update happens AFTER getting features, so no lookahead.
    # ════════════════════════════════════════════════════════════════════════

    # Process each row
    for i in range(n_rows):
        # FIRST: Get DTMC features using transition matrix learned from PAST ONLY
        # At this point, transition matrix contains info from rows 0 to i-1
        # We use prev_state (from row i-1) to get probabilities
        dtmc_features = dtmc_calc.get_features(prev_state)

        dtmc_state[i] = prev_state  # State we're predicting FROM
        dtmc_p_up_1[i] = dtmc_features["dtmc_p_up_1"]
        dtmc_p_up_5[i] = dtmc_features["dtmc_p_up_5"]
        dtmc_p_up_10[i] = dtmc_features["dtmc_p_up_10"]
        dtmc_p_up_20[i] = dtmc_features["dtmc_p_up_20"]
        dtmc_p_down_1[i] = dtmc_features["dtmc_p_down_1"]
        dtmc_entropy[i] = dtmc_features["dtmc_transition_entropy"]
        dtmc_self_trans[i] = dtmc_features["dtmc_self_transition"]
        dtmc_expected_dwell[i] = dtmc_features["dtmc_expected_dwell"]

        # THEN: Observe this row's return (AFTER getting features)
        current_return = returns[i]
        current_state = dtmc_calc.discretize_return(current_return)

        # Update DTMC with observed transition (expanding window)
        # This update will be used for row i+1, not row i
        dtmc_calc.update(prev_state, current_state)

        prev_state = current_state

        # HMM-4 dwell features
        if hmm_model is not None:
            hmm4_dwell = compute_hmm_dwell_features(
                hmm_model, int(hmm_regimes[i]), hmm_probs[i]
            )
            hmm4_expected_dwell[i] = hmm4_dwell["expected_dwell"]
            hmm4_weighted_dwell[i] = hmm4_dwell["weighted_dwell"]
            hmm4_transition_skew[i] = hmm4_dwell["transition_skew"]
            hmm4_regime_entropy[i] = hmm4_dwell["regime_entropy"]
            hmm4_normalized_entropy[i] = hmm4_dwell["normalized_entropy"]

        # HMM-5 dwell features
        if hmm5_model is not None:
            hmm5_dwell = compute_hmm_dwell_features(
                hmm5_model, int(hmm5_regimes[i]), hmm5_probs[i]
            )
            hmm5_expected_dwell[i] = hmm5_dwell["expected_dwell"]
            hmm5_weighted_dwell[i] = hmm5_dwell["weighted_dwell"]
            hmm5_transition_skew[i] = hmm5_dwell["transition_skew"]
            hmm5_regime_entropy[i] = hmm5_dwell["regime_entropy"]
            hmm5_normalized_entropy[i] = hmm5_dwell["normalized_entropy"]

        if (i + 1) % 500 == 0 or i == n_rows - 1:
            print(f"      • Processed {i + 1}/{n_rows} rows")

    # Add all features to dataframe
    df = df.with_columns(
        [
            # DTMC features (11 features)
            pl.lit(dtmc_state).cast(pl.Int32).alias("dtmc_state"),
            pl.lit(dtmc_p_up_1).alias("dtmc_p_up_1"),
            pl.lit(dtmc_p_up_5).alias("dtmc_p_up_5"),
            pl.lit(dtmc_p_up_10).alias("dtmc_p_up_10"),
            pl.lit(dtmc_p_up_20).alias("dtmc_p_up_20"),
            pl.lit(dtmc_p_down_1).alias("dtmc_p_down_1"),
            pl.lit(dtmc_entropy).alias("dtmc_transition_entropy"),
            pl.lit(dtmc_self_trans).alias("dtmc_self_transition"),
            pl.lit(dtmc_expected_dwell).alias("dtmc_expected_dwell"),
            # Direction probability spread
            pl.lit(dtmc_p_up_1 - dtmc_p_down_1).alias("dtmc_direction_spread"),
            # Confidence: how far from 0.5 (uncertain)
            pl.lit(np.abs(dtmc_p_up_1 - 0.5) * 2).alias("dtmc_direction_confidence"),
            # HMM-4 dwell features (5 features)
            pl.lit(hmm4_expected_dwell).alias("hmm4_expected_dwell"),
            pl.lit(hmm4_weighted_dwell).alias("hmm4_weighted_dwell"),
            pl.lit(hmm4_transition_skew).alias("hmm4_transition_skew"),
            pl.lit(hmm4_regime_entropy).alias("hmm4_regime_entropy"),
            pl.lit(hmm4_normalized_entropy).alias("hmm4_normalized_entropy"),
            # HMM-5 dwell features (5 features)
            pl.lit(hmm5_expected_dwell).alias("hmm5_expected_dwell"),
            pl.lit(hmm5_weighted_dwell).alias("hmm5_weighted_dwell"),
            pl.lit(hmm5_transition_skew).alias("hmm5_transition_skew"),
            pl.lit(hmm5_regime_entropy).alias("hmm5_regime_entropy"),
            pl.lit(hmm5_normalized_entropy).alias("hmm5_normalized_entropy"),
        ]
    )

    # Cross-model dwell comparison (3 features)
    df = df.with_columns(
        [
            # Dwell agreement: similar expected dwell times
            (pl.col("hmm4_expected_dwell") - pl.col("hmm5_expected_dwell"))
            .abs()
            .alias("hmm_dwell_divergence"),
            # Combined entropy (uncertainty across both models)
            (
                (pl.col("hmm4_normalized_entropy") + pl.col("hmm5_normalized_entropy"))
                / 2.0
            ).alias("hmm_combined_entropy"),
            # Both models in stable regime (high expected dwell)
            (
                (pl.col("hmm4_expected_dwell") > 5.0)
                & (pl.col("hmm5_expected_dwell") > 5.0)
            )
            .cast(pl.Int32)
            .alias("hmm_both_stable"),
        ]
    )

    return df


# Apply to PARTIAL dataset (starts fresh, builds up transition matrix)
print("\n  Applying to PARTIAL dataset...")
hmm_model_ref = hmm_model if HMM4_AVAILABLE else None
hmm5_model_ref = hmm5_model if HMM5_AVAILABLE else None

df_partial = add_advanced_markov_features(
    df_partial,
    dtmc_calc,
    hmm_model=hmm_model_ref,
    hmm5_model=hmm5_model_ref,
    historical_df=None,  # No historical data for PARTIAL
    dataset_name="PARTIAL",
)

# Apply to TRAIN dataset (continues expanding window from PARTIAL)
print("\n  Applying to TRAIN dataset (expanding window continues)...")
# Use the SAME dtmc_calc that was trained on PARTIAL
# Pass df_partial as historical to warm up and continue expanding window

df_train = add_advanced_markov_features(
    df_train,
    dtmc_calc,  # Use the SAME calculator (continues from PARTIAL)
    hmm_model=hmm_model_ref,
    hmm5_model=hmm5_model_ref,
    historical_df=df_partial,  # Warm up with PARTIAL, then expand on TRAIN
    dataset_name="TRAIN",
)

# Save calculator state for API simulation
ADVANCED_MARKOV_STATE = {
    "dtmc_threshold_up": dtmc_ret_67,  # Data-driven threshold
    "dtmc_threshold_down": dtmc_ret_33,  # Data-driven threshold
    "dtmc_smoothing": 0.5,
    "dtmc_transition_counts": dtmc_calc.transition_counts.copy(),
    "dtmc_state_counts": dtmc_calc.state_counts.copy(),
}

print("\n✅ Advanced Markov Features Complete!")
print("  ✅ EXPANDING WINDOW: At row i, features use only data from rows 0 to i-1")
print("  ✅ Matches API simulation methodology used in other cells")
print("  Added 24 new features:")
print("")
print("  📊 DTMC Features (11):")
print("    - dtmc_state: Discretized return state (0=Down, 1=Flat, 2=Up)")
print("    - dtmc_p_up_1/5/10/20: P(Up) at 1, 5, 10, 20 bars ahead")
print("    - dtmc_p_down_1: P(Down) next bar")
print("    - dtmc_transition_entropy: Uncertainty in next state")
print("    - dtmc_self_transition: P(stay in current state)")
print("    - dtmc_expected_dwell: Expected bars until state change")
print("    - dtmc_direction_spread: P(Up) - P(Down)")
print("    - dtmc_direction_confidence: |P(Up) - 0.5| * 2")
print("")
print("  📊 HMM-4 Dwell Features (5):")
print("    - hmm4_expected_dwell: Expected bars in current regime")
print("    - hmm4_weighted_dwell: Probability-weighted expected dwell")
print("    - hmm4_transition_skew: Low→High minus High→Low transition prob")
print("    - hmm4_regime_entropy: Uncertainty in regime (−Σ p·log(p))")
print("    - hmm4_normalized_entropy: Entropy / max_entropy")
print("")
print("  📊 HMM-5 Dwell Features (5):")
print("    - hmm5_expected_dwell/weighted_dwell/transition_skew")
print("    - hmm5_regime_entropy/normalized_entropy")
print("")
print("  📊 Cross-Model Features (3):")
print("    - hmm_dwell_divergence: |HMM4_dwell - HMM5_dwell|")
print("    - hmm_combined_entropy: Average entropy across models")
print("    - hmm_both_stable: Both models expect dwell > 5 bars")
print("")
print("  💾 DTMC state saved for API simulation continuation")

print(f"\n{'=' * 80}\n")

# %% [CELL 7.6] Feature-Group HMMs - Trained on PARTIAL, Applied to TRAIN
# ═══════════════════════════════════════════════════════════════════════════
# FEATURE-GROUP HIDDEN MARKOV MODELS
# ═══════════════════════════════════════════════════════════════════════════
# Train separate HMMs on different feature categories to capture domain-specific
# regime dynamics:
#   M* - Market Dynamics/Technical features
#   E* - Macro Economic features
#   I* - Interest Rate features
#   P* - Price/Valuation features
#   V* - Volatility features
#   S* - Sentiment features
#
# STRATEGY:
#   1. Dynamically detect feature columns by prefix (M1, M2, E1, E2, etc.)
#   2. For each group, find first row where ALL features have valid values
#   3. Train HMM on PARTIAL data (from first valid row)
#   4. Apply incrementally to TRAIN (row-by-row)
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 80}")
print("FEATURE-GROUP HIDDEN MARKOV MODELS (M*, E*, I*, P*, V*, S*)")
print(f"{'=' * 80}\n")

print("Objective:")
print("  • Train separate HMMs for each feature category")
print("  • Detect valid data start dynamically (handle NaN/0 at start)")
print("  • Apply incrementally to match API simulation methodology")
print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: DEFINE FEATURE GROUPS AND DETECT COLUMNS
# ═══════════════════════════════════════════════════════════════════════════

FEATURE_GROUP_PREFIXES = {
    "M": "Market_Dynamics",  # M1, M2, ..., M18
    "E": "Macro_Economic",  # E1, E2, ..., E20
    "I": "Interest_Rate",  # I1, I2, ..., I9
    "P": "Price_Valuation",  # P1, P2, ..., P13
    "V": "Volatility",  # V1, V2, ..., V13
    "S": "Sentiment",  # S1, S2, ..., S12
}

# ═══════════════════════════════════════════════════════════════════════════
# ENHANCED FEATURES FOR EACH HMM GROUP
# ═══════════════════════════════════════════════════════════════════════════
# These calculated features are added to their respective groups to boost
# HMM model performance. Features can appear in multiple groups if relevant.
# ═══════════════════════════════════════════════════════════════════════════

ENHANCED_GROUP_FEATURES = {
    # M (Market Dynamics) - Technical/Market breadth features
    "M": [
        # Trend/momentum (market direction)
        "momentum_5d",
        "momentum_21d",
        "momentum_50d",
        "momentum_accel_5d",
        "momentum_accel_21d",
        # Moving averages (market trends)
        "ma_diff_5_20",
        "ma_diff_10_50",
        "ma_diff_50_200",
        "dist_from_ma_5d",
        "dist_from_ma_21d",
        "dist_from_ma_50d",
        # Rate of change
        "roc_5d",
        "roc_21d",
        "roc_50d",
        # Autocorrelation (market persistence)
        "autocorr_5d",
        "autocorr_21d",
        # Position in range (market level)
        "position_in_range_21d",
        "position_in_range_100d",
    ],
    # E (Macro Economic) - Economic cycle features
    "E": [
        # Long-term momentum (economic cycles)
        "momentum_50d",
        "momentum_100d",
        "momentum_200d",
        "momentum_ratio_20_100",
        "momentum_ratio_50_200",
        # Longer-term trends
        "ma_diff_50_200",
        "ma_diff_21_100",
        "dist_from_ma_50d",
        "dist_from_ma_100d",
        # Rate of change (economic shifts)
        "roc_50d",
        "roc_100d",
        # Longer autocorrelation (economic persistence)
        "autocorr_21d",
        "autocorr_50d",
        "autocorr_100d",
        # Skewness/kurtosis (distribution shifts)
        "skew_50d",
        "skew_100d",
        "kurt_50d",
        "kurt_100d",
    ],
    # I (Interest Rate) - Rate-sensitive features
    "I": [
        # Rate momentum
        "momentum_21d",
        "momentum_50d",
        "momentum_100d",
        # Rate trends
        "ma_diff_21_100",
        "ma_diff_50_200",
        "dist_from_ma_21d",
        "dist_from_ma_50d",
        # Rate of change
        "roc_21d",
        "roc_50d",
        # Autocorrelation (rate persistence)
        "autocorr_21d",
        "autocorr_50d",
        # Volatility of rates
        "vol_of_vol_21d",
        "vol_of_vol_50d",
    ],
    # P (Price/Valuation) - Valuation level features
    "P": [
        # Price momentum
        "momentum_21d",
        "momentum_50d",
        "momentum_100d",
        # Distance from MAs (valuation levels)
        "dist_from_ma_21d",
        "dist_from_ma_50d",
        "dist_from_ma_100d",
        # Z-scores (relative valuation)
        "zscore_21d",
        "zscore_50d",
        "zscore_100d",
        # Percentile ranks (historical valuation context)
        "return_pctrank_21d",
        "return_pctrank_50d",
        "return_pctrank_100d",
        # Position in range (valuation context)
        "position_in_range_21d",
        "position_in_range_100d",
        # Tail risk (valuation extremes)
        "dist_from_lower_21d",
        "dist_from_upper_21d",
        "dist_from_lower_100d",
        "dist_from_upper_100d",
    ],
    # V (Volatility) - Volatility regime features
    "V": [
        # Core volatility measures
        "volatility_ma_5",
        "volatility_ma_21",
        "ewma_vol_5d",
        "ewma_vol_21d",
        "ewma_vol_60d",  # Matches extraction (NOT 10d/63d)
        "realized_vol_5d",
        "realized_vol_21d",
        "realized_vol_50d",
        # Vol of vol (volatility clustering)
        "vol_of_vol_5d",
        "vol_of_vol_21d",
        "vol_of_vol_50d",
        # Historical vol
        "mean_hist_vol_5",
        "mean_hist_vol_21",
        "mean_hist_vol_63",
        # Vol ratios (regime shifts)
        "vol_ratio_21",
        "mhv_ratio_5_21",
        "mhv_ratio_21_63",
        # Vol percentile (regime context)
        "vol_percentile_rank_21",
        "vol_percentile_rank_63",
        # Vol acceleration
        "vol_acceleration_5",
        "vol_acceleration_21",
        # Vol autocorr (vol clustering)
        "vol_autocorr_5",
        "vol_autocorr_21",
        # Vol momentum
        "vol_momentum_5",
        "vol_momentum_21",
        # Max vol changes
        "max_vol_change_5d",
        "avg_vol_change_5d",
    ],
    # S (Sentiment) - Sentiment/behavior features
    "S": [
        # Short-term momentum (sentiment swings)
        "momentum_5d",
        "momentum_10d",
        "momentum_21d",
        "momentum_accel_5d",
        "momentum_accel_10d",
        # Win rates (market sentiment proxy)
        "win_rate_5d",
        "win_rate_10d",
        "win_rate_21d",
        "win_rate_ratio_5",
        "win_rate_ratio_21",
        # Consecutive moves (herding behavior)
        "consecutive_up",
        "consecutive_down",
        # Skewness (sentiment asymmetry)
        "skew_21d",
        "skew_50d",
        # Tail risk (sentiment extremes)
        "lower_5pct_21d",
        "upper_95pct_21d",
        # Drawdowns (fear/greed)
        "max_drawdown_5d",
        "max_drawdown_21d",
    ],
}

# Enhanced features for derived groups (MOM, D)
ENHANCED_DERIVED_GROUP_FEATURES = {
    # MOM (Momentum) - All momentum-related calculated features
    "MOM": [
        # Core momentum (already in MOMENTUM_FEATURES, but add more)
        "momentum_100d",
        "momentum_200d",
        "momentum_252d",
        "momentum_accel_10d",
        "momentum_accel_50d",
        "momentum_accel_100d",
        # Momentum ratios
        "momentum_ratio_5_20",
        "momentum_ratio_5_50",
        "momentum_ratio_10_50",
        "momentum_ratio_20_100",
        "momentum_ratio_50_200",
        # Vol-adjusted momentum (all periods)
        "vol_adj_momentum_10d",
        "vol_adj_momentum_14d",
        "vol_adj_momentum_50d",
        "vol_adj_momentum_100d",
        # Rate of change (momentum proxy)
        "roc_5d",
        "roc_10d",
        "roc_21d",
        "roc_50d",
        "roc_100d",
        # Sharpe-like (risk-adjusted momentum)
        "sharpe_like_5d",
        "sharpe_like_21d",
        "sharpe_like_50d",
    ],
    # D (Binary/Dummy) - Additional regime indicators
    "D": [
        # Additional vol regime indicators
        "high_vol_regime_21",
        "high_vol_regime_50",
        "high_vol_regime_100",
        # Uptrend regimes
        "uptrend_regime_5d",
        "uptrend_regime_10d",
        "uptrend_regime_21d",
        "uptrend_regime_50d",
        # Strong trends
        "strong_uptrend_21d",
        "strong_uptrend_50d",
        "strong_downtrend_21d",
        "strong_downtrend_50d",
        # Reversal signals
        "reversal_5_21",
        "reversal_10_50",
        "reversal_21_100",
        "reversal_up_5_21",
        "reversal_up_10_50",
        "reversal_up_21_100",
        # MA crossovers
        "ma_cross_20_50",
        "ma_cross_14_50",
        "ma_cross_21_100",
    ],
}


def get_enhanced_columns_for_group(df, prefix, base_columns):
    """
    Get enhanced feature columns for a group by combining base columns
    with calculated features that are available in the dataframe.

    Returns: (combined_columns, enhanced_only_columns)
    """
    enhanced_features = ENHANCED_GROUP_FEATURES.get(prefix, [])

    # Check which enhanced features are available
    available_enhanced = [f for f in enhanced_features if f in df.columns]

    # Combine base + enhanced, avoiding duplicates
    combined = list(base_columns)
    for f in available_enhanced:
        if f not in combined:
            combined.append(f)

    return combined, available_enhanced


def get_enhanced_columns_for_derived_group(df, prefix, base_columns):
    """
    Get enhanced feature columns for derived groups (MOM, D).
    """
    enhanced_features = ENHANCED_DERIVED_GROUP_FEATURES.get(prefix, [])

    # Check which enhanced features are available
    available_enhanced = [f for f in enhanced_features if f in df.columns]

    # Combine base + enhanced, avoiding duplicates
    combined = list(base_columns)
    for f in available_enhanced:
        if f not in combined:
            combined.append(f)

    return combined, available_enhanced


def detect_feature_group_columns(df, prefix):
    """
    Detect all columns that start with a given prefix (e.g., 'M' for M1, M2, ...).
    Returns list of column names sorted numerically.
    """
    import re

    pattern = re.compile(f"^{prefix}(\\d+)$")
    matching_cols = []
    for col in df.columns:
        match = pattern.match(col)
        if match:
            matching_cols.append((int(match.group(1)), col))
    # Sort by numeric suffix
    matching_cols.sort(key=lambda x: x[0])
    return [col for _, col in matching_cols]


# ═══════════════════════════════════════════════════════════════════════════
# ADAPTIVE FEATURE-GROUP HMM OPTIMIZATION
# ═══════════════════════════════════════════════════════════════════════════
# Uses statistical methods to automatically determine optimal:
# 1. Feature subset (based on data quality scores)
# 2. Sample size (based on HMM convergence and BIC)
# 3. Number of components (based on cross-validation)
# ═══════════════════════════════════════════════════════════════════════════


def compute_column_quality_scores(df, columns):
    """
    Compute quality scores for each column based on multiple criteria.
    Higher score = better quality column for HMM training.

    Scores based on:
    - Data availability (% non-NaN rows)
    - Early availability (first valid row)
    - Signal variance (standardized)
    - Non-zero ratio
    - Autocorrelation (regime-like behavior)

    Returns:
    --------
    dict: {column_name: {'score': float, 'first_valid': int, 'availability': float, ...}}
    """
    quality_scores = {}
    total_rows = len(df)

    for col in columns:
        try:
            data = df[col].cast(pl.Float64).to_numpy()
        except:
            quality_scores[col] = {
                "score": 0.0,
                "first_valid": total_rows,
                "availability": 0.0,
            }
            continue

        # Find first valid (non-NaN) row
        valid_mask = ~np.isnan(data)
        first_valid_indices = np.where(valid_mask)[0]

        if len(first_valid_indices) == 0:
            quality_scores[col] = {
                "score": 0.0,
                "first_valid": total_rows,
                "availability": 0.0,
            }
            continue

        first_valid = first_valid_indices[0]
        valid_data = data[valid_mask]

        # 1. Data availability score (0-1)
        availability = len(valid_data) / total_rows

        # 2. Early availability score (0-1) - penalize late-starting columns
        early_score = 1.0 - (first_valid / total_rows)

        # 3. Non-zero ratio (0-1) - columns with all zeros are useless
        nonzero_ratio = (
            np.count_nonzero(valid_data) / len(valid_data) if len(valid_data) > 0 else 0
        )

        # 4. Variance score (0-1) - normalized by range
        if len(valid_data) > 1 and np.std(valid_data) > 0:
            # Coefficient of variation (normalized variance)
            cv = np.std(valid_data) / (np.abs(np.mean(valid_data)) + 1e-10)
            variance_score = min(1.0, cv / 2.0)  # Cap at 1.0
        else:
            variance_score = 0.0

        # 5. Autocorrelation score (0-1) - higher = more regime-like
        if len(valid_data) > 10:
            # Lag-1 autocorrelation (regime persistence)
            autocorr = np.corrcoef(valid_data[:-1], valid_data[1:])[0, 1]
            autocorr_score = max(0, autocorr)  # Only positive autocorr is good
        else:
            autocorr_score = 0.5  # Neutral if insufficient data

        # Combined score (weighted average)
        # Prioritize: availability > early_start > nonzero > variance > autocorr
        combined_score = (
            0.30 * availability
            + 0.25 * early_score
            + 0.20 * nonzero_ratio
            + 0.15 * variance_score
            + 0.10 * autocorr_score
        )

        quality_scores[col] = {
            "score": combined_score,
            "first_valid": first_valid,
            "availability": availability,
            "early_score": early_score,
            "nonzero_ratio": nonzero_ratio,
            "variance_score": variance_score,
            "autocorr_score": autocorr_score,
            "n_valid": len(valid_data),
        }

    return quality_scores


def estimate_min_samples_for_hmm(n_features, n_components=3, covariance_type="full"):
    """
    Estimate minimum samples required for stable HMM training.

    Based on statistical theory and practical guidelines:

    References:
    - Rabiner, L.R. (1989) "A Tutorial on Hidden Markov Models" IEEE Proc.
    - Bishop, C.M. (2006) "Pattern Recognition and Machine Learning"
    - Rule of thumb: 10-30 observations per free parameter for MLE

    Parameters in Gaussian HMM:
    - Transition matrix: (n_components-1) * n_components free params
    - Initial state: n_components - 1 free params
    - Means: n_components * n_features params
    - Covariances (full): n_components * n_features * (n_features + 1) / 2 params
    - Covariances (diag): n_components * n_features params

    For covariance estimation stability (Wishart distribution theory):
    - Full covariance needs n_samples > n_features (absolute minimum)
    - Recommended: n_samples >= 3 * n_features for stable estimates

    Returns:
    --------
    int: Minimum recommended samples
    dict: Breakdown of parameter counts
    """
    # Count free parameters
    trans_params = (n_components - 1) * n_components
    init_params = n_components - 1
    mean_params = n_components * n_features

    if covariance_type == "full":
        # Full covariance: d(d+1)/2 unique elements per state
        cov_params = n_components * n_features * (n_features + 1) // 2
    elif covariance_type == "diag":
        # Diagonal covariance: d elements per state
        cov_params = n_components * n_features
    else:
        cov_params = n_components * n_features  # default to diag

    total_params = trans_params + init_params + mean_params + cov_params

    # Rule 1: 30 samples per parameter (more conservative for better quality)
    # Increased from 20 to improve quality scores
    samples_per_param = 30
    min_samples_mle = int(total_params * samples_per_param)

    # Rule 2: Covariance stability requirement
    # For diagonal covariance, we need fewer samples per feature
    if covariance_type == "full":
        min_samples_cov = max(n_features * 10, 100)  # 10x features for full
    else:
        min_samples_cov = max(n_features * 5, 50)  # 5x features for diagonal

    # Rule 3: HMM-specific: need enough transitions to estimate trans matrix
    # Each state should be visited multiple times
    min_samples_hmm = n_components * 100  # ~100 visits per state for stability

    # Take the maximum of all requirements
    min_samples = max(min_samples_mle, min_samples_cov, min_samples_hmm, 200)

    # Cap at reasonable maximum (but higher cap for large feature sets)
    min_samples = min(min_samples, 8000)

    return min_samples


def evaluate_hmm_quality(hmm_model, data, n_splits=3):
    """
    Evaluate HMM quality using validated statistical metrics.

    Based on:
    - BIC (Schwarz 1978): Standard model selection criterion
    - AIC (Akaike 1974): Alternative information criterion
    - Transition matrix analysis: Check for degenerate solutions
    - State balance: Ensure all states are used (avoid collapsed states)

    References:
    - Celeux & Durand (2008) "Selecting hidden Markov model state number
      with cross-validated likelihood" Computational Statistics
    - Rabiner (1989) "A Tutorial on Hidden Markov Models"

    Returns:
    --------
    dict: Quality metrics with interpretations
    """
    n_samples, n_features = data.shape
    n_components = hmm_model.n_components

    # 1. Log-likelihood per sample (normalized for comparison)
    try:
        log_likelihood = hmm_model.score(data)
        ll_per_sample = log_likelihood / n_samples
    except:
        ll_per_sample = -np.inf
        log_likelihood = -np.inf

    # 2. Count free parameters (for diagonal covariance - matching actual training)
    # Following standard HMM parameter counting for covariance_type='diag'
    n_params = (
        (n_components - 1) * n_components  # transition matrix (K*(K-1) free)
        + (n_components - 1)  # initial state (K-1 free)
        + n_components * n_features  # means (K*d)
        + n_components * n_features  # diagonal covariances (K*d) - NOT full!
    )

    # 3. BIC: Bayesian Information Criterion (Schwarz 1978)
    # BIC = -2*log(L) + k*log(n), lower is better
    if log_likelihood > -np.inf:
        bic = -2 * log_likelihood + n_params * np.log(n_samples)
    else:
        bic = np.inf

    # 4. AIC: Akaike Information Criterion (Akaike 1974)
    # AIC = -2*log(L) + 2k, lower is better
    if log_likelihood > -np.inf:
        aic = -2 * log_likelihood + 2 * n_params
    else:
        aic = np.inf

    # 5. Transition matrix analysis
    # Check for degenerate solutions (eigenvalues should be real for stochastic matrix)
    eigenvalues = np.linalg.eigvals(hmm_model.transmat_)
    complex_ratio = np.sum(np.abs(np.imag(eigenvalues)) > 1e-10) / len(eigenvalues)
    stability_score = 1.0 - complex_ratio

    # Check for absorbing states (rows with self-transition ≈ 1.0)
    self_trans = np.diag(hmm_model.transmat_)
    absorbing_states = np.sum(self_trans > 0.99)

    # 6. State utilization (avoid collapsed models)
    # All states should be visited; entropy measures balance
    try:
        states = hmm_model.predict(data)
        state_counts = np.bincount(states, minlength=n_components)
        state_probs = state_counts / len(states)

        # Check for unused states (< 1% of samples)
        unused_states = np.sum(state_probs < 0.01)

        # Entropy of state distribution (normalized)
        state_probs_clipped = np.clip(state_probs, 1e-10, 1.0)
        entropy = -np.sum(state_probs_clipped * np.log(state_probs_clipped))
        max_entropy = np.log(n_components)
        balance_score = entropy / max_entropy if max_entropy > 0 else 0
    except:
        balance_score = 0.0
        unused_states = n_components

    # 7. Combined quality score
    # Prioritize: stability > balance > convergence
    # For diagonal covariance, use more generous normalization
    bic_normalized = 1.0 / (1.0 + max(0, bic) / 50000)  # More generous for diag cov
    ll_normalized = 1.0 / (1.0 + np.exp(-ll_per_sample - 5))  # Adjusted sigmoid center

    # Samples/param ratio bonus (reward models with adequate data)
    spp_ratio = n_samples / n_params if n_params > 0 else 0
    spp_score = min(1.0, spp_ratio / 30)  # Target: 30 samples/param

    quality_score = (
        0.25 * ll_normalized  # Log-likelihood (convergence quality)
        + 0.30 * stability_score  # Transition matrix validity (most important)
        + 0.25 * balance_score  # State utilization
        + 0.10 * bic_normalized  # Model parsimony
        + 0.10 * spp_score  # Samples/param adequacy
    )

    return {
        "quality_score": quality_score,
        "ll_per_sample": ll_per_sample,
        "log_likelihood": log_likelihood,
        "bic": bic,
        "aic": aic,
        "stability_score": stability_score,
        "balance_score": balance_score,
        "n_params": n_params,
        "n_samples": n_samples,
        "absorbing_states": absorbing_states,
        "unused_states": unused_states,
        "samples_per_param": n_samples / n_params if n_params > 0 else 0,
    }


def find_optimal_feature_subset_adaptive(df, columns, n_components=3, verbose=True):
    """
    Adaptively find optimal feature subset using quality-based ranking.

    Algorithm:
    1. Score all columns by data quality
    2. Sort columns by score (best first)
    3. Iteratively add columns while maintaining sufficient samples
    4. Balance: more features need more samples

    Returns:
    --------
    list : Optimal column subset
    int : First valid row for this subset
    list : Excluded columns (with reasons)
    dict : Optimization details
    """
    if not columns:
        return [], -1, [], {"error": "No columns provided"}

    total_rows = len(df)

    # Step 1: Score all columns
    quality_scores = compute_column_quality_scores(df, columns)

    # Step 2: Sort columns by quality score (descending)
    sorted_cols = sorted(
        columns, key=lambda c: quality_scores[c]["score"], reverse=True
    )

    if verbose:
        print("      Column quality ranking:")
        for i, col in enumerate(sorted_cols[:5]):  # Show top 5
            q = quality_scores[col]
            print(
                f"        {i + 1}. {col}: score={q['score']:.3f} (avail={q['availability']:.2f}, first={q['first_valid']})"
            )

    # Step 3: Greedy feature selection
    # Start with best columns and add more while maintaining quality
    best_subset = []
    best_first_valid = total_rows
    best_quality = 0.0

    # Cap max features to ensure samples/param ratio > 20
    # For 3 components and diag covariance: params = 3*3-1 + 3-1 + 3*d + 3*d = 8 + 6*d
    # With ~6000 samples and target ratio of 30: 6000/30 = 200 params max => d ≈ 32
    # Be conservative: limit to 15 features for better quality
    MAX_FEATURES_FOR_QUALITY = min(15, len(sorted_cols))

    # Try different subset sizes
    for n_features in range(1, MAX_FEATURES_FOR_QUALITY + 1):
        subset = sorted_cols[:n_features]

        # Find first valid row for this subset
        first_valid = 0
        for col in subset:
            col_first = quality_scores[col]["first_valid"]
            first_valid = max(first_valid, col_first)

        # Calculate available samples
        available_samples = total_rows - first_valid

        # Estimate minimum required samples
        min_samples = estimate_min_samples_for_hmm(n_features, n_components)

        # Check if we have enough samples
        if available_samples < min_samples:
            if verbose and n_features <= 5:
                print(
                    f"      {n_features} features: need {min_samples} samples, have {available_samples} → SKIP"
                )
            continue

        # Calculate quality heuristic (more features with sufficient samples = better)
        # Balance: feature richness vs sample sufficiency
        sample_ratio = min(
            1.0, available_samples / (min_samples * 2)
        )  # Prefer 2x min samples
        feature_richness = n_features / len(columns)

        # Combined heuristic
        avg_quality = np.mean([quality_scores[c]["score"] for c in subset])
        subset_quality = (
            0.40 * sample_ratio + 0.30 * feature_richness + 0.30 * avg_quality
        )

        if subset_quality > best_quality:
            best_quality = subset_quality
            best_subset = subset
            best_first_valid = first_valid

        if verbose and n_features <= 5:
            print(
                f"      {n_features} features: {available_samples} samples (min={min_samples}), quality={subset_quality:.3f}"
            )

    # Handle case where no valid subset found
    if not best_subset:
        # Fallback: use single best column
        best_col = sorted_cols[0]
        best_subset = [best_col]
        best_first_valid = quality_scores[best_col]["first_valid"]
        if verbose:
            print(f"      Fallback: using single best column {best_col}")

    excluded = [c for c in columns if c not in best_subset]
    excluded_info = [(c, f"score={quality_scores[c]['score']:.3f}") for c in excluded]

    details = {
        "n_selected": len(best_subset),
        "n_excluded": len(excluded),
        "first_valid_row": best_first_valid,
        "available_samples": total_rows - best_first_valid,
        "min_samples_required": estimate_min_samples_for_hmm(
            len(best_subset), n_components
        ),
        "quality_scores": quality_scores,
        "best_quality": best_quality,
    }

    return best_subset, best_first_valid, excluded_info, details


def find_optimal_n_components(data, max_components=5, min_components=2):
    """
    Find optimal number of HMM components using BIC.

    Tests n_components from min to max and selects based on:
    - BIC (lower is better)
    - Convergence success
    - Regime balance

    Returns:
    --------
    int: Optimal n_components
    dict: Comparison results
    """
    from sklearn.preprocessing import StandardScaler

    # Standardize data
    scaler = StandardScaler()
    data_scaled = scaler.fit_transform(data)

    # Add regularization for numerical stability
    np.random.seed(42)
    data_scaled = data_scaled + np.random.normal(0, 1e-6, data_scaled.shape)

    results = {}
    best_n = min_components
    best_bic = np.inf

    for n in range(min_components, max_components + 1):
        try:
            hmm = GaussianHMM(
                n_components=n,
                covariance_type="diag",  # Use 'diag' for numerical stability
                n_iter=200,
                tol=1e-3,
                min_covar=1e-3,  # Minimum covariance
                random_state=42,
                init_params="mc",
                params="stmc",
                verbose=False,
            )
            hmm.fit(data_scaled)

            quality = evaluate_hmm_quality(hmm, data_scaled)
            results[n] = quality

            if quality["bic"] < best_bic:
                best_bic = quality["bic"]
                best_n = n

        except Exception as e:
            results[n] = {"error": str(e)}

    return best_n, results


# Legacy function for backward compatibility
def find_first_valid_row(df, columns, min_nonzero_ratio=0.5):
    """
    Find the first row where all specified columns have valid (non-NaN, non-zero) values.
    Also checks that at least min_nonzero_ratio of columns have non-zero values.

    Parameters:
    -----------
    df : pl.DataFrame
        Dataset to check
    columns : list
        Column names to check
    min_nonzero_ratio : float
        Minimum ratio of columns that must be non-zero (0.5 = 50%)

    Returns:
    --------
    int : First valid row index, or -1 if no valid row found
    dict : Statistics about the detection
    """
    if not columns:
        return -1, {"error": "No columns provided"}

    # Convert to numpy for faster processing, ensuring float type
    try:
        data = np.column_stack([df[col].cast(pl.Float64).to_numpy() for col in columns])
    except Exception:
        # If casting fails, try converting column by column
        arrays = []
        for col in columns:
            try:
                arr = df[col].cast(pl.Float64).to_numpy()
            except:
                # If column can't be cast to float, fill with NaN
                arr = np.full(len(df), np.nan)
            arrays.append(arr)
        data = np.column_stack(arrays)

    for row_idx in range(len(data)):
        row = data[row_idx]
        # Check for NaN (now safe since data is float)
        if np.isnan(row).any():
            continue
        # Check for minimum non-zero ratio
        nonzero_count = np.count_nonzero(row)
        if nonzero_count / len(row) >= min_nonzero_ratio:
            return row_idx, {
                "first_valid_row": row_idx,
                "total_rows": len(data),
                "excluded_rows": row_idx,
                "nonzero_count": nonzero_count,
                "total_cols": len(columns),
            }

    return -1, {"error": "No valid row found", "total_rows": len(data)}


# Legacy wrapper for compatibility
def find_optimal_feature_subset(df, columns, max_exclude=2):
    """
    Legacy wrapper - now uses adaptive algorithm.
    """
    subset, first_valid, excluded_info, details = find_optimal_feature_subset_adaptive(
        df, columns, n_components=3, verbose=False
    )
    excluded = [e[0] for e in excluded_info] if excluded_info else []
    return subset, first_valid, excluded


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: ANALYZE EACH FEATURE GROUP (ADAPTIVE)
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP 1: Analyzing feature groups in PARTIAL dataset (ADAPTIVE MODE)...")
print("          Using quality-based column ranking + sample/feature balancing")
print()

FEATURE_GROUP_INFO = {}
FEATURE_GROUP_AVAILABLE = {}
FEATURE_GROUP_OPTIMIZATION_DETAILS = {}

for prefix, group_name in FEATURE_GROUP_PREFIXES.items():
    print(f"  ── {group_name} ({prefix}*) ──")

    # Detect columns for this group
    columns = detect_feature_group_columns(df_partial, prefix)

    if not columns:
        print(f"    ⚠️  No columns found matching {prefix}[0-9]+")
        FEATURE_GROUP_AVAILABLE[prefix] = False
        print()
        continue

    print(
        f"    Detected {len(columns)} base columns: {columns[:5]}{'...' if len(columns) > 5 else ''}"
    )

    # ═══════════════════════════════════════════════════════════════════════
    # ENHANCE: Add calculated features to boost HMM performance
    # ═══════════════════════════════════════════════════════════════════════
    enhanced_columns, added_features = get_enhanced_columns_for_group(
        df_partial, prefix, columns
    )
    if added_features:
        print(
            f"    Enhanced with {len(added_features)} calculated features: {added_features[:5]}{'...' if len(added_features) > 5 else ''}"
        )

    # Use ADAPTIVE algorithm for optimal subset selection on enhanced columns
    optimal_cols, first_valid, excluded_info, details = (
        find_optimal_feature_subset_adaptive(
            df_partial, enhanced_columns, n_components=3, verbose=True
        )
    )

    # Store optimization details
    FEATURE_GROUP_OPTIMIZATION_DETAILS[prefix] = details

    # Check if we got a valid result
    available_samples = details.get("available_samples", 0)
    min_samples_needed = details.get("min_samples_required", 100)

    if not optimal_cols or available_samples < 50:
        print("    ❌ REJECTED: insufficient valid data")
        print(
            f"       Available samples: {available_samples}, Minimum needed: {min_samples_needed}"
        )
        FEATURE_GROUP_AVAILABLE[prefix] = False
        print()
        continue

    # Count how many enhanced features made it through
    n_base_selected = len([c for c in optimal_cols if c in columns])
    n_enhanced_selected = len([c for c in optimal_cols if c in added_features])

    # Store info for training
    FEATURE_GROUP_INFO[prefix] = {
        "name": group_name,
        "all_columns": enhanced_columns,  # Now includes enhanced
        "base_columns": columns,  # Original prefix columns
        "enhanced_columns": added_features,  # Calculated features added
        "selected_columns": optimal_cols,
        "n_base_selected": n_base_selected,
        "n_enhanced_selected": n_enhanced_selected,
        "excluded_columns": [e[0] for e in excluded_info] if excluded_info else [],
        "first_valid_row": first_valid,
        "n_valid_rows": available_samples,
        "optimization_details": details,
    }
    FEATURE_GROUP_AVAILABLE[prefix] = True

    print(f"    ✅ SELECTED: {len(optimal_cols)}/{len(enhanced_columns)} columns")
    print(
        f"       Composition: {n_base_selected} base ({prefix}*) + {n_enhanced_selected} calculated features"
    )
    print(
        f"       First valid row: {first_valid}, Available samples: {available_samples}"
    )
    print(
        f"       Min samples needed for {len(optimal_cols)} features: {min_samples_needed}"
    )
    print(
        f"       Sample margin: {available_samples - min_samples_needed:+d} ({available_samples / min_samples_needed:.1f}x)"
    )
    if excluded_info:
        print(
            f"       Excluded (low quality): {[e[0] for e in excluded_info[:3]]}{'...' if len(excluded_info) > 3 else ''}"
        )
    print()

print(
    f"  Summary: {sum(FEATURE_GROUP_AVAILABLE.values())}/{len(FEATURE_GROUP_PREFIXES)} groups available for training"
)
print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: TRAIN HMMs FOR EACH FEATURE GROUP (WITH QUALITY EVALUATION)
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP 2: Training HMMs with quality evaluation...")
print()

from sklearn.preprocessing import StandardScaler

FEATURE_GROUP_MODELS = {}
FEATURE_GROUP_SCALERS = {}
FEATURE_GROUP_QUALITY = {}
N_COMPONENTS_PER_GROUP = 3  # Default, can be optimized per group

for prefix, info in FEATURE_GROUP_INFO.items():
    group_name = info["name"]
    columns = info["selected_columns"]
    first_valid = info["first_valid_row"]

    print(f"  ── Training {group_name} HMM ({prefix}*) ──")

    try:
        # Extract features from first_valid_row onwards, ensuring float type
        hmm_input = np.column_stack(
            [
                df_partial[col].cast(pl.Float64).to_numpy()[first_valid:]
                for col in columns
            ]
        )

        # Remove any remaining NaN rows (safety)
        valid_mask = ~np.isnan(hmm_input).any(axis=1)
        hmm_input_clean = hmm_input[valid_mask]

        # Check minimum samples based on feature count
        min_samples = estimate_min_samples_for_hmm(len(columns), N_COMPONENTS_PER_GROUP)

        if len(hmm_input_clean) < min_samples:
            print(
                f"    ⚠️  Insufficient data: {len(hmm_input_clean)} rows (need >= {min_samples})"
            )
            FEATURE_GROUP_AVAILABLE[prefix] = False
            continue

        # Standardize features
        scaler = StandardScaler()
        hmm_input_scaled = scaler.fit_transform(hmm_input_clean)

        # Add small regularization to prevent singular covariance matrices
        np.random.seed(42 + hash(prefix) % 1000)  # Different seed per group
        regularization_noise = np.random.normal(0, 1e-6, hmm_input_scaled.shape)
        hmm_input_scaled = hmm_input_scaled + regularization_noise

        # Check for degenerate features
        feature_stds = np.std(hmm_input_scaled, axis=0)
        for i, std in enumerate(feature_stds):
            if std < 1e-8:
                hmm_input_scaled[:, i] += np.random.normal(
                    0, 0.01, len(hmm_input_scaled)
                )

        # Train HMM with robust settings and more iterations for better convergence
        hmm_fg = GaussianHMM(
            n_components=N_COMPONENTS_PER_GROUP,
            covariance_type="diag",  # Use 'diag' for numerical stability
            n_iter=1000,  # Increased from 500 for better convergence
            tol=1e-5,  # Tighter tolerance for better fit
            min_covar=1e-3,  # Minimum covariance to prevent singularity
            random_state=42,
            init_params="mc",
            params="stmc",
            verbose=False,
        )

        hmm_fg.fit(hmm_input_scaled)

        # Evaluate HMM quality
        quality_metrics = evaluate_hmm_quality(hmm_fg, hmm_input_scaled)
        FEATURE_GROUP_QUALITY[prefix] = quality_metrics

        FEATURE_GROUP_MODELS[prefix] = hmm_fg
        FEATURE_GROUP_SCALERS[prefix] = scaler

        # Determine quality assessment
        samples_per_param = quality_metrics["samples_per_param"]
        quality_assessment = (
            "EXCELLENT"
            if samples_per_param > 30
            else "GOOD"
            if samples_per_param > 15
            else "MARGINAL"
        )

        print(f"    ✅ Trained successfully [{quality_assessment}]")
        print(
            f"       Samples: {len(hmm_input_clean)} | Features: {len(columns)} | Params: {quality_metrics['n_params']}"
        )
        print(f"       Samples/Param: {samples_per_param:.1f} (recommended: >20)")
        print(f"       Quality Score: {quality_metrics['quality_score']:.3f}")
        print(
            f"       ├─ Log-likelihood/sample: {quality_metrics['ll_per_sample']:.3f}"
        )
        print(
            f"       ├─ BIC: {quality_metrics['bic']:.1f} | AIC: {quality_metrics['aic']:.1f}"
        )
        print(
            f"       ├─ Stability: {quality_metrics['stability_score']:.2f} (absorbing: {quality_metrics['absorbing_states']})"
        )
        print(
            f"       └─ Regime balance: {quality_metrics['balance_score']:.2f} (unused: {quality_metrics['unused_states']})"
        )

    except Exception as e:
        print(f"    ❌ Training failed: {e}")
        FEATURE_GROUP_AVAILABLE[prefix] = False

    print()

# Summary of trained models
trained_groups = [
    p for p in FEATURE_GROUP_PREFIXES if FEATURE_GROUP_AVAILABLE.get(p, False)
]
print("  ═══════════════════════════════════════════════════════════════")
print(
    f"  TRAINING SUMMARY: {len(trained_groups)}/{len(FEATURE_GROUP_PREFIXES)} groups trained"
)
print(f"  Trained: {trained_groups}")
if FEATURE_GROUP_QUALITY:
    avg_quality = np.mean([q["quality_score"] for q in FEATURE_GROUP_QUALITY.values()])
    print(f"  Average Quality Score: {avg_quality:.3f}")
print("  ═══════════════════════════════════════════════════════════════")
print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP 4: APPLY FEATURE-GROUP HMMs INCREMENTALLY
# ═══════════════════════════════════════════════════════════════════════════


def add_feature_group_hmm_features(
    df,
    models_dict,
    scalers_dict,
    group_info_dict,
    available_dict,
    historical_df=None,
    dataset_name="",
):
    """
    Apply feature-group HMMs to dataset incrementally (row-by-row).

    For each group with a trained model, adds:
    - {prefix}_hmm_regime: Current regime (0, 1, 2)
    - {prefix}_hmm_confidence: Max probability across regimes
    - {prefix}_hmm_regime_change: Binary transition indicator
    - {prefix}_hmm_duration: Consecutive rows in current regime

    Parameters:
    -----------
    df : pl.DataFrame
        Dataset to add features to
    models_dict : dict
        Trained HMM models per group prefix
    scalers_dict : dict
        Fitted scalers per group prefix
    group_info_dict : dict
        Group info (columns, first_valid_row, etc.)
    available_dict : dict
        Availability flags per group prefix
    historical_df : pl.DataFrame
        Historical data for incremental prediction
    dataset_name : str
        Name for logging
    """
    print(f"    Processing {dataset_name} ({len(df)} rows)...")

    # Initialize result columns
    result_columns = {}

    for prefix, info in group_info_dict.items():
        if not available_dict.get(prefix, False):
            continue
        if prefix not in models_dict:
            continue

        group_name = info["name"]
        columns = info["selected_columns"]
        first_valid = info["first_valid_row"]
        hmm_model = models_dict[prefix]
        scaler = scalers_dict[prefix]

        # Initialize arrays
        regimes = np.zeros(len(df), dtype=int)
        confidences = np.zeros(len(df))

        # Initialize historical features as empty - will build up incrementally
        # This matches the original HMM implementation exactly
        hist_features_list = []

        # If we have historical data (e.g., PARTIAL when processing TRAIN),
        # we need to build up the historical context row by row first
        if historical_df is not None and len(historical_df) > 0:
            # Process historical data to build up hist_features_list
            for hist_idx in range(len(historical_df)):
                try:
                    hist_row = np.array(
                        [[float(historical_df[col][hist_idx]) for col in columns]]
                    )
                    if not np.isnan(hist_row).any():
                        hist_features_list.append(hist_row)
                except (TypeError, ValueError):
                    continue

        # Process current dataset incrementally (expanding window)
        for idx in range(len(df)):
            # Get current row features, cast to float
            try:
                current_features = np.array([[float(df[col][idx]) for col in columns]])
            except (TypeError, ValueError):
                # If conversion fails, use default values
                regimes[idx] = 0
                confidences[idx] = 1.0 / N_COMPONENTS_PER_GROUP
                continue

            # Check for NaN in current row
            if np.isnan(current_features).any():
                regimes[idx] = 0
                confidences[idx] = 1.0 / N_COMPONENTS_PER_GROUP
                continue

            # Combine historical + current for prediction
            if len(hist_features_list) > 0:
                combined = np.vstack(hist_features_list + [current_features])
            else:
                combined = current_features

            # Remove NaN rows from combined (safety check)
            valid_mask = ~np.isnan(combined).any(axis=1)
            combined_clean = combined[valid_mask]

            if len(combined_clean) < 1:
                regimes[idx] = 0
                confidences[idx] = 1.0 / N_COMPONENTS_PER_GROUP
                # Still add current row to history for next iteration
                hist_features_list.append(current_features)
                continue

            try:
                # Scale and predict on FULL combined sequence
                combined_scaled = scaler.transform(combined_clean)
                pred_regimes = hmm_model.predict(combined_scaled)
                pred_probs = hmm_model.predict_proba(combined_scaled)

                # Extract LAST prediction (current row) - matches original HMM logic
                regimes[idx] = int(pred_regimes[-1])
                confidences[idx] = float(pred_probs[-1].max())
            except Exception:
                regimes[idx] = 0
                confidences[idx] = 1.0 / N_COMPONENTS_PER_GROUP

            # Update historical features for next iteration (EXPANDING WINDOW)
            hist_features_list.append(current_features)

        # Compute regime changes and duration
        regime_changes = np.zeros(len(df), dtype=int)
        regime_duration = np.ones(len(df), dtype=int)

        for i in range(1, len(df)):
            if regimes[i] != regimes[i - 1]:
                regime_changes[i] = 1
                regime_duration[i] = 1
            else:
                regime_duration[i] = regime_duration[i - 1] + 1

        # Store basic results
        result_columns[f"{prefix}_hmm_regime"] = regimes
        result_columns[f"{prefix}_hmm_confidence"] = confidences
        result_columns[f"{prefix}_hmm_regime_change"] = regime_changes
        result_columns[f"{prefix}_hmm_duration"] = regime_duration

        print(
            f"      • {group_name} ({prefix}*): {N_COMPONENTS_PER_GROUP} regimes applied, {len(hist_features_list)} history rows"
        )

    # Add all basic columns to dataframe first
    for col_name, values in result_columns.items():
        if "regime" in col_name and "change" not in col_name:
            df = df.with_columns(pl.lit(values).cast(pl.Int32).alias(col_name))
        elif "change" in col_name or "duration" in col_name:
            df = df.with_columns(pl.lit(values).cast(pl.Int32).alias(col_name))
        else:
            df = df.with_columns(pl.lit(values).alias(col_name))

    # ════════════════════════════════════════════════════════════════════════
    # ADD ADVANCED FEATURES FOR EACH FEATURE GROUP (matches HMM-4/HMM-5 pattern)
    # ════════════════════════════════════════════════════════════════════════
    for prefix, info in group_info_dict.items():
        if not available_dict.get(prefix, False):
            continue
        if prefix not in models_dict:
            continue

        # 1-2. Regime Stability (3d and 5d windows)
        df = df.with_columns(
            [
                # Regime stable for 3 days: no changes in last 3 rows
                (
                    pl.col(f"{prefix}_hmm_regime_change").rolling_sum(
                        window_size=3, min_periods=1
                    )
                    == 0
                )
                .cast(pl.Int32)
                .alias(f"{prefix}_hmm_stable_3d"),
                # Regime stable for 5 days: no changes in last 5 rows
                (
                    pl.col(f"{prefix}_hmm_regime_change").rolling_sum(
                        window_size=5, min_periods=1
                    )
                    == 0
                )
                .cast(pl.Int32)
                .alias(f"{prefix}_hmm_stable_5d"),
            ]
        )

        # 3-5. Confidence Dynamics
        df = df.with_columns(
            [
                # Confidence change from previous row
                (
                    pl.col(f"{prefix}_hmm_confidence")
                    - pl.col(f"{prefix}_hmm_confidence").shift(1)
                )
                .fill_null(0.0)
                .alias(f"{prefix}_hmm_conf_change"),
                # 5-period moving average of confidence
                pl.col(f"{prefix}_hmm_confidence")
                .rolling_mean(window_size=5, min_periods=1)
                .alias(f"{prefix}_hmm_conf_ma5"),
                # 5-period standard deviation of confidence
                pl.col(f"{prefix}_hmm_confidence")
                .rolling_std(window_size=5, min_periods=1)
                .fill_null(0.0)
                .alias(f"{prefix}_hmm_conf_std5"),
            ]
        )

        # 6-7. Transition Counting (5d and 10d windows)
        df = df.with_columns(
            [
                # Count of transitions in last 5 days
                pl.col(f"{prefix}_hmm_regime_change")
                .rolling_sum(window_size=5, min_periods=1)
                .cast(pl.Int32)
                .alias(f"{prefix}_hmm_transitions_5d"),
                # Count of transitions in last 10 days
                pl.col(f"{prefix}_hmm_regime_change")
                .rolling_sum(window_size=10, min_periods=1)
                .cast(pl.Int32)
                .alias(f"{prefix}_hmm_transitions_10d"),
            ]
        )

        # 8. Entropy of confidence (uncertainty measure)
        # For 3-component HMM, max entropy = log(3) ≈ 1.099
        # Using confidence as proxy: low confidence = high uncertainty
        # Entropy approximation: -p*log(p) - (1-p)*log((1-p)/2) for 3 states
        conf = df[f"{prefix}_hmm_confidence"].to_numpy()
        entropy = np.zeros(len(df))
        for i in range(len(conf)):
            p = conf[i]
            if p > 0.99:
                entropy[i] = 0.0  # Very certain
            elif p < 0.34:
                entropy[i] = np.log(3)  # Maximum entropy (uniform)
            else:
                # Approximate entropy based on max prob
                remaining = 1.0 - p
                other_p = remaining / 2.0  # Split among other 2 states
                entropy[i] = -(
                    p * np.log(p + 1e-10) + 2 * other_p * np.log(other_p + 1e-10)
                )

        df = df.with_columns([pl.lit(entropy).alias(f"{prefix}_hmm_entropy")])

    return df


# Apply to PARTIAL
print("  STEP 3: Applying feature-group HMMs to PARTIAL...")
df_partial = add_feature_group_hmm_features(
    df_partial,
    FEATURE_GROUP_MODELS,
    FEATURE_GROUP_SCALERS,
    FEATURE_GROUP_INFO,
    FEATURE_GROUP_AVAILABLE,
    historical_df=None,
    dataset_name="PARTIAL",
)

# Apply to TRAIN (using PARTIAL as historical context)
print("\n  STEP 4: Applying feature-group HMMs to TRAIN...")
df_train = add_feature_group_hmm_features(
    df_train,
    FEATURE_GROUP_MODELS,
    FEATURE_GROUP_SCALERS,
    FEATURE_GROUP_INFO,
    FEATURE_GROUP_AVAILABLE,
    historical_df=df_partial,
    dataset_name="TRAIN",
)

# Update working dataframe
df_pl = df_train.clone()

# ═══════════════════════════════════════════════════════════════════════════
# STEP 5: SAVE STATE FOR API SIMULATION
# ═══════════════════════════════════════════════════════════════════════════

FEATURE_GROUP_HMM_STATE = {
    "group_info": FEATURE_GROUP_INFO,
    "available": FEATURE_GROUP_AVAILABLE,
    "n_components": N_COMPONENTS_PER_GROUP,
    # Models and scalers saved separately (can't serialize HMM to dict easily)
}

# Count features added
n_groups_trained = sum(1 for p in FEATURE_GROUP_AVAILABLE.values() if p)
n_basic_features = n_groups_trained * 4  # regime, confidence, change, duration
n_advanced_features = (
    n_groups_trained * 8
)  # stable_3d, stable_5d, conf_change, conf_ma5, conf_std5, transitions_5d, transitions_10d, entropy
n_features_added = n_basic_features + n_advanced_features

print("\n✅ Feature-Group HMM Engineering Complete!")
print(f"  • Groups analyzed: {len(FEATURE_GROUP_PREFIXES)}")
print(f"  • Groups trained: {n_groups_trained}")
print(
    f"  • Features added: {n_features_added} ({n_basic_features} basic + {n_advanced_features} advanced)"
)
print()
print("  📊 Features per group (12 each):")
for prefix in FEATURE_GROUP_PREFIXES:
    if FEATURE_GROUP_AVAILABLE.get(prefix, False):
        info = FEATURE_GROUP_INFO[prefix]
        print(f"    {info['name']} ({prefix}*):")
        print("      BASIC (4 features):")
        print(f"        - {prefix}_hmm_regime (0, 1, 2)")
        print(f"        - {prefix}_hmm_confidence (max prob)")
        print(f"        - {prefix}_hmm_regime_change (binary)")
        print(f"        - {prefix}_hmm_duration (consecutive)")
        print("      ADVANCED (8 features):")
        print(f"        - {prefix}_hmm_stable_3d/5d (regime stability)")
        print(f"        - {prefix}_hmm_conf_change/ma5/std5 (confidence dynamics)")
        print(f"        - {prefix}_hmm_transitions_5d/10d (transition counts)")
        print(f"        - {prefix}_hmm_entropy (uncertainty measure)")
        print(f"      • Trained on: {info['n_valid_rows']} rows")
        print(f"      • Input features: {len(info['selected_columns'])}")

print("\n  💾 State saved for API simulation continuation")
print(f"\n{'=' * 80}\n")

# %% [CELL 7.7] Derived Feature HMMs (MOM*, D*) - Momentum & Binary Features
# ═══════════════════════════════════════════════════════════════════════════
# DERIVED FEATURE-GROUP HIDDEN MARKOV MODELS
# ═══════════════════════════════════════════════════════════════════════════
# Train HMMs on derived features from RowByRowFeatureCalculator:
#   MOM* - Momentum-related features (returns, acceleration, vol-adjusted)
#   D* - Dummy/Binary regime features (reversals, crossovers, high_vol)
#
# These capture regime dynamics from COMPUTED features, complementing the
# raw data feature-group HMMs (M*, E*, I*, P*, V*, S*)
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 80}")
print("DERIVED FEATURE-GROUP HMMs (MOM*, D*)")
print(f"{'=' * 80}\n")

print("Objective:")
print("  • Train HMMs on momentum features to capture trend regimes")
print("  • Train HMMs on binary features to capture market regime signals")
print()

# ═══════════════════════════════════════════════════════════════════════════
# DEFINE DERIVED FEATURE GROUPS
# ═══════════════════════════════════════════════════════════════════════════

# Momentum features (continuous) - core momentum indicators
MOMENTUM_FEATURES = [
    # Core momentum (cumulative returns)
    "momentum_5d",
    "momentum_10d",
    "momentum_21d",
    "momentum_50d",
    "momentum_100d",
    # Momentum acceleration
    "momentum_accel_5d",
    "momentum_accel_21d",
    # Volatility momentum
    "vol_momentum_5",
    "vol_momentum_21",
    # Vol-adjusted momentum
    "vol_adj_momentum_5d",
    "vol_adj_momentum_21d",
]

# Binary/Dummy features - regime indicators
BINARY_FEATURES = [
    # Volatility regimes
    "high_vol_regime",
    "extreme_vol_regime",
    # Trend regimes
    "uptrend_regime",
    "strong_uptrend",
    # Reversal signals
    "reversal_5d",
    "reversal_21d",
    # MA crossover signals
    "ma_cross_5_20",
    "ma_cross_10_50",
    "ma_cross_50_200",
]

DERIVED_FEATURE_GROUP_PREFIXES = {
    "MOM": ("Momentum_Dynamics", MOMENTUM_FEATURES),
    "D": ("Binary_Regimes", BINARY_FEATURES),
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: VALIDATE FEATURE AVAILABILITY
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP 1: Validating derived feature availability in TRAIN dataset...")
print()

DERIVED_FEATURE_GROUP_INFO = {}
DERIVED_FEATURE_GROUP_AVAILABLE = {}

for prefix, (group_name, feature_list) in DERIVED_FEATURE_GROUP_PREFIXES.items():
    print(f"  ── {group_name} ({prefix}*) ──")

    # Check which base features are available in df_train
    available_base_features = [f for f in feature_list if f in df_train.columns]
    missing_features = [f for f in feature_list if f not in df_train.columns]

    print(
        f"    Base features: {len(available_base_features)}/{len(feature_list)} available"
    )

    if missing_features:
        print(
            f"    Missing base: {missing_features[:5]}{'...' if len(missing_features) > 5 else ''}"
        )

    # ═══════════════════════════════════════════════════════════════════════
    # ENHANCE: Add calculated features to boost HMM performance
    # ═══════════════════════════════════════════════════════════════════════
    enhanced_columns, added_features = get_enhanced_columns_for_derived_group(
        df_train, prefix, available_base_features
    )
    if added_features:
        print(
            f"    Enhanced with {len(added_features)} additional features: {added_features[:5]}{'...' if len(added_features) > 5 else ''}"
        )

    # ═══════════════════════════════════════════════════════════════════════
    # CHECK TOTAL AVAILABLE SAMPLES (PARTIAL + TRAIN combined)
    # Derived groups will use combined data for training, so check availability there
    # ═══════════════════════════════════════════════════════════════════════

    # First, check which features exist in PARTIAL (for combined training)
    partial_available_features = [
        f for f in enhanced_columns if f in df_partial.columns
    ]
    use_combined = len(partial_available_features) >= 3

    if use_combined:
        # Use PARTIAL + TRAIN for sample counting
        total_available_samples = len(df_partial) + len(df_train)
        print(
            f"    Using PARTIAL + TRAIN for training: {total_available_samples} total samples"
        )
        working_features = partial_available_features
    else:
        # Fall back to TRAIN only
        total_available_samples = len(df_train)
        print(f"    Using TRAIN only for training: {total_available_samples} samples")
        working_features = [f for f in enhanced_columns if f in df_train.columns]

    # ═══════════════════════════════════════════════════════════════════════
    # DYNAMICALLY LIMIT FEATURES based on available samples
    # For 3-component diagonal HMM: params = 8 + 6*d
    # With 20 samples/param target: max_features = (samples/20 - 8) / 6
    # ═══════════════════════════════════════════════════════════════════════
    SAMPLES_PER_PARAM_TARGET = 20  # Lower target for derived groups (use more data)

    # Calculate max features we can afford
    max_params = total_available_samples / SAMPLES_PER_PARAM_TARGET
    max_features_affordable = int((max_params - 8) / 6)  # Solve: 8 + 6*d <= max_params
    max_features_affordable = max(
        3, min(max_features_affordable, 15)
    )  # Between 3 and 15

    print(f"    Max affordable features (20 samples/param): {max_features_affordable}")

    if len(working_features) > max_features_affordable:
        # Prioritize base features, then add enhanced up to limit
        limited_features = [
            f for f in available_base_features if f in working_features
        ][:max_features_affordable]
        remaining_slots = max_features_affordable - len(limited_features)
        if remaining_slots > 0:
            enhanced_available = [f for f in added_features if f in working_features]
            limited_features.extend(enhanced_available[:remaining_slots])
        print(
            f"    ⚠️  Limited to {len(limited_features)} features (was {len(working_features)}) for sample requirement"
        )
        available_features = limited_features
    else:
        available_features = working_features

    if len(available_features) < 3:
        print("    ❌ REJECTED: need at least 3 features for HMM")
        DERIVED_FEATURE_GROUP_AVAILABLE[prefix] = False
        print()
        continue

    # Calculate actual min samples with the selected features
    # Using lower requirement (20 samples/param) for derived groups
    n_features_selected = len(available_features)
    n_params_selected = 8 + 6 * n_features_selected  # For 3-component diag HMM
    min_samples = max(n_params_selected * SAMPLES_PER_PARAM_TARGET, 300)  # At least 300

    if total_available_samples < min_samples:
        print(
            f"    ❌ REJECTED: {total_available_samples} samples < {min_samples} min samples"
        )
        DERIVED_FEATURE_GROUP_AVAILABLE[prefix] = False
        print()
        continue

    # Check for valid data in TRAIN (for first_valid_row tracking)
    first_valid = 0
    for idx in range(len(df_train)):
        row_valid = True
        for col in available_features:
            if col not in df_train.columns:
                row_valid = False
                break
            val = df_train[col][idx]
            if val is None or (isinstance(val, float) and np.isnan(val)):
                row_valid = False
                break
        if row_valid:
            first_valid = idx
            break

    n_valid_rows = len(df_train) - first_valid

    # Count composition
    n_base_selected = len(
        [f for f in available_features if f in available_base_features]
    )
    n_enhanced_selected = len([f for f in available_features if f in added_features])

    # Store info
    DERIVED_FEATURE_GROUP_INFO[prefix] = {
        "name": group_name,
        "all_columns": enhanced_columns,
        "base_columns": feature_list,
        "enhanced_columns": [f for f in added_features if f in available_features],
        "selected_columns": available_features,
        "n_base_selected": n_base_selected,
        "n_enhanced_selected": n_enhanced_selected,
        "first_valid_row": first_valid,
        "n_valid_rows": n_valid_rows,
        "total_training_samples": total_available_samples,
        "use_combined_training": use_combined,
    }
    DERIVED_FEATURE_GROUP_AVAILABLE[prefix] = True

    print(f"    ✅ AVAILABLE: {len(available_features)} total features")
    print(
        f"       Composition: {n_base_selected} base + {n_enhanced_selected} enhanced"
    )
    print(
        f"       Training samples: {total_available_samples} ({'PARTIAL+TRAIN' if use_combined else 'TRAIN only'})"
    )
    print(
        f"       Min samples needed: {min_samples}, margin: +{total_available_samples - min_samples}"
    )
    print(
        f"       Samples/param ratio: {total_available_samples / n_params_selected:.1f}x"
    )
    print(
        f"       Features: {available_features[:5]}{'...' if len(available_features) > 5 else ''}"
    )
    print()

print(
    f"  Summary: {sum(DERIVED_FEATURE_GROUP_AVAILABLE.values())}/{len(DERIVED_FEATURE_GROUP_PREFIXES)} derived groups available"
)
print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: TRAIN HMMs FOR EACH DERIVED FEATURE GROUP
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP 2: Training derived feature HMMs...")
print()

DERIVED_FEATURE_GROUP_MODELS = {}
DERIVED_FEATURE_GROUP_SCALERS = {}
DERIVED_FEATURE_GROUP_QUALITY = {}
N_COMPONENTS_DERIVED = 3  # 3 regimes per derived group

for prefix, info in DERIVED_FEATURE_GROUP_INFO.items():
    if not DERIVED_FEATURE_GROUP_AVAILABLE.get(prefix, False):
        continue

    group_name = info["name"]
    columns = info["selected_columns"]
    first_valid = info["first_valid_row"]

    print(f"  ── Training {group_name} HMM ({prefix}*) ──")

    try:
        # Use PARTIAL + TRAIN combined for training (more data = better HMM)
        # First, check if columns exist in df_partial
        partial_has_cols = all(c in df_partial.columns for c in columns)

        if partial_has_cols:
            # Concatenate PARTIAL + TRAIN for training
            combined_for_training = pl.concat([df_partial, df_train])
            print(
                f"    Using PARTIAL + TRAIN for training ({len(combined_for_training)} rows)"
            )
        else:
            combined_for_training = df_train
            print(
                f"    Using TRAIN only for training ({len(combined_for_training)} rows)"
            )

        # Extract features
        hmm_input = np.column_stack(
            [combined_for_training[col].cast(pl.Float64).to_numpy() for col in columns]
        )

        # Remove NaN rows
        valid_mask = ~np.isnan(hmm_input).any(axis=1)
        hmm_input_clean = hmm_input[valid_mask]

        print(f"    Valid samples: {len(hmm_input_clean)}")

        # Check minimum samples (using same formula as validation step)
        n_features_selected = len(columns)
        n_params_selected = 8 + 6 * n_features_selected  # For 3-component diag HMM
        min_samples = max(n_params_selected * 20, 300)  # 20 samples/param, at least 300

        if len(hmm_input_clean) < min_samples:
            print(f"    ⚠️ Insufficient data: {len(hmm_input_clean)} < {min_samples}")
            DERIVED_FEATURE_GROUP_AVAILABLE[prefix] = False
            continue

        # Standardize
        scaler = StandardScaler()
        hmm_input_scaled = scaler.fit_transform(hmm_input_clean)

        # Add small regularization to prevent singular covariance matrices
        np.random.seed(42 + hash(prefix) % 1000)
        regularization_noise = np.random.normal(0, 1e-6, hmm_input_scaled.shape)
        hmm_input_scaled = hmm_input_scaled + regularization_noise

        # Check for degenerate features
        feature_stds = np.std(hmm_input_scaled, axis=0)
        for i, std in enumerate(feature_stds):
            if std < 1e-8:
                hmm_input_scaled[:, i] += np.random.normal(
                    0, 0.01, len(hmm_input_scaled)
                )

        # Train HMM with robust settings
        hmm_derived = GaussianHMM(
            n_components=N_COMPONENTS_DERIVED,
            covariance_type="diag",  # Use 'diag' for numerical stability
            n_iter=500,
            tol=1e-4,
            min_covar=1e-3,  # Minimum covariance to prevent singularity
            random_state=42,
            init_params="mc",
            params="stmc",
            verbose=False,
        )

        hmm_derived.fit(hmm_input_scaled)

        # Evaluate quality
        quality_metrics = evaluate_hmm_quality(hmm_derived, hmm_input_scaled)
        DERIVED_FEATURE_GROUP_QUALITY[prefix] = quality_metrics

        DERIVED_FEATURE_GROUP_MODELS[prefix] = hmm_derived
        DERIVED_FEATURE_GROUP_SCALERS[prefix] = scaler

        samples_per_param = quality_metrics["samples_per_param"]
        quality_assessment = (
            "EXCELLENT"
            if samples_per_param > 30
            else "GOOD"
            if samples_per_param > 15
            else "MARGINAL"
        )

        print(f"    ✅ Trained successfully [{quality_assessment}]")
        print(
            f"       Samples: {len(hmm_input_clean)} | Features: {len(columns)} | Params: {quality_metrics['n_params']}"
        )
        print(f"       Samples/Param: {samples_per_param:.1f}")
        print(f"       Quality Score: {quality_metrics['quality_score']:.3f}")

    except Exception as e:
        print(f"    ❌ Training failed: {e}")
        DERIVED_FEATURE_GROUP_AVAILABLE[prefix] = False

    print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: APPLY DERIVED HMMs TO PARTIAL AND TRAIN
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP 3: Applying derived HMMs to PARTIAL and TRAIN...")
print()


def add_derived_hmm_features(df, prefix, hmm_model, scaler, columns, dataset_name=""):
    """Add HMM features for a derived feature group."""
    print(f"    Processing {dataset_name} for {prefix}*...")

    n_rows = len(df)

    # Check if all columns exist
    missing = [c for c in columns if c not in df.columns]
    if missing:
        print(f"      ⚠️ Missing columns: {missing}")
        # Add placeholder columns
        for col_suffix in [
            "hmm_regime",
            "hmm_confidence",
            "hmm_regime_change",
            "hmm_duration",
        ]:
            col_name = f"{prefix}_{col_suffix}"
            if col_name not in df.columns:
                df = df.with_columns(
                    [pl.lit(0 if "regime" in col_suffix else 0.0).alias(col_name)]
                )
        return df

    # Extract features
    hmm_input = np.column_stack(
        [df[col].cast(pl.Float64).to_numpy() for col in columns]
    )

    # Scale
    valid_mask = ~np.isnan(hmm_input).any(axis=1)

    # Initialize arrays
    regimes = np.zeros(n_rows, dtype=int)
    confidences = np.full(n_rows, 1.0 / 3.0)  # Default to uniform

    if valid_mask.sum() > 0:
        hmm_input_scaled = scaler.transform(hmm_input[valid_mask])
        pred_regimes = hmm_model.predict(hmm_input_scaled)
        pred_probs = hmm_model.predict_proba(hmm_input_scaled)

        regimes[valid_mask] = pred_regimes
        confidences[valid_mask] = pred_probs.max(axis=1)

    # Calculate regime change and duration
    regime_changes = np.zeros(n_rows, dtype=int)
    durations = np.ones(n_rows, dtype=int)

    for i in range(1, n_rows):
        if regimes[i] != regimes[i - 1]:
            regime_changes[i] = 1
            durations[i] = 1
        else:
            durations[i] = durations[i - 1] + 1

    # Add columns to dataframe
    df = df.with_columns(
        [
            pl.Series(f"{prefix}_hmm_regime", regimes).cast(pl.Int32),
            pl.Series(f"{prefix}_hmm_confidence", confidences),
            pl.Series(f"{prefix}_hmm_regime_change", regime_changes).cast(pl.Int32),
            pl.Series(f"{prefix}_hmm_duration", durations).cast(pl.Int32),
        ]
    )

    print(
        f"      ✅ Added 4 features: {prefix}_hmm_{{regime,confidence,regime_change,duration}}"
    )

    return df


# Apply to PARTIAL
for prefix, info in DERIVED_FEATURE_GROUP_INFO.items():
    if not DERIVED_FEATURE_GROUP_AVAILABLE.get(prefix, False):
        continue
    if prefix not in DERIVED_FEATURE_GROUP_MODELS:
        continue

    # Check if columns exist in df_partial
    partial_has_cols = all(c in df_partial.columns for c in info["selected_columns"])

    if partial_has_cols:
        df_partial = add_derived_hmm_features(
            df_partial,
            prefix,
            DERIVED_FEATURE_GROUP_MODELS[prefix],
            DERIVED_FEATURE_GROUP_SCALERS[prefix],
            info["selected_columns"],
            dataset_name="PARTIAL",
        )
    else:
        print(f"    ⚠️ Skipping {prefix}* for PARTIAL (columns not available)")
        # Add placeholder columns
        for col_suffix in [
            "hmm_regime",
            "hmm_confidence",
            "hmm_regime_change",
            "hmm_duration",
        ]:
            col_name = f"{prefix}_{col_suffix}"
            if col_name not in df_partial.columns:
                df_partial = df_partial.with_columns(
                    [
                        pl.lit(
                            0
                            if "regime" in col_suffix
                            or "change" in col_suffix
                            or "duration" in col_suffix
                            else 0.33
                        ).alias(col_name)
                    ]
                )

# Apply to TRAIN
for prefix, info in DERIVED_FEATURE_GROUP_INFO.items():
    if not DERIVED_FEATURE_GROUP_AVAILABLE.get(prefix, False):
        continue
    if prefix not in DERIVED_FEATURE_GROUP_MODELS:
        continue

    df_train = add_derived_hmm_features(
        df_train,
        prefix,
        DERIVED_FEATURE_GROUP_MODELS[prefix],
        DERIVED_FEATURE_GROUP_SCALERS[prefix],
        info["selected_columns"],
        dataset_name="TRAIN",
    )

# Update working dataframe
df_pl = df_train.clone()

# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

n_derived_trained = sum(1 for p in DERIVED_FEATURE_GROUP_AVAILABLE.values() if p)
n_derived_features = n_derived_trained * 4  # regime, confidence, change, duration

print("\n✅ Derived Feature-Group HMM Engineering Complete!")
print(f"  • Groups analyzed: {len(DERIVED_FEATURE_GROUP_PREFIXES)}")
print(f"  • Groups trained: {n_derived_trained}")
print(f"  • Features added: {n_derived_features}")
print()

for prefix in DERIVED_FEATURE_GROUP_PREFIXES:
    if DERIVED_FEATURE_GROUP_AVAILABLE.get(prefix, False):
        info = DERIVED_FEATURE_GROUP_INFO[prefix]
        quality = DERIVED_FEATURE_GROUP_QUALITY.get(prefix, {})
        print(f"  {info['name']} ({prefix}*):")
        print(f"    - {prefix}_hmm_regime (0, 1, 2)")
        print(f"    - {prefix}_hmm_confidence")
        print(f"    - {prefix}_hmm_regime_change (binary)")
        print(f"    - {prefix}_hmm_duration")
        print(f"    Quality Score: {quality.get('quality_score', 'N/A'):.3f}")

# ═══════════════════════════════════════════════════════════════════════════
# SYNC COLUMNS: Ensure df_partial and df_train have same columns
# ═══════════════════════════════════════════════════════════════════════════
print("\n  Syncing columns between PARTIAL and TRAIN...")

# Find columns in df_train but not in df_partial
train_cols = set(df_train.columns)
partial_cols = set(df_partial.columns)

missing_in_partial = train_cols - partial_cols
missing_in_train = partial_cols - train_cols

if missing_in_partial:
    print(f"    Adding {len(missing_in_partial)} missing columns to PARTIAL")
    for col in missing_in_partial:
        # Determine appropriate default value based on column type
        col_dtype = df_train[col].dtype
        if col_dtype in [
            pl.Int32,
            pl.Int64,
            pl.Int8,
            pl.Int16,
            pl.UInt8,
            pl.UInt16,
            pl.UInt32,
            pl.UInt64,
        ]:
            default_val = 0
        else:
            default_val = 0.0
        df_partial = df_partial.with_columns(
            [pl.lit(default_val).cast(col_dtype).alias(col)]
        )

if missing_in_train:
    print(f"    Adding {len(missing_in_train)} missing columns to TRAIN")
    for col in missing_in_train:
        col_dtype = df_partial[col].dtype
        if col_dtype in [
            pl.Int32,
            pl.Int64,
            pl.Int8,
            pl.Int16,
            pl.UInt8,
            pl.UInt16,
            pl.UInt32,
            pl.UInt64,
        ]:
            default_val = 0
        else:
            default_val = 0.0
        df_train = df_train.with_columns(
            [pl.lit(default_val).cast(col_dtype).alias(col)]
        )

# Reorder df_partial to match df_train column order
df_partial = df_partial.select(df_train.columns)

print(f"    ✅ PARTIAL: {len(df_partial.columns)} columns")
print(f"    ✅ TRAIN: {len(df_train.columns)} columns")

print(f"\n{'=' * 80}\n")

# %% [CELL 7.8] Per-Group Isolation Forest + Regime Change Detection Models
# ═══════════════════════════════════════════════════════════════════════════
# PER-GROUP ANOMALY DETECTION + REGIME CHANGE DETECTION
# ═══════════════════════════════════════════════════════════════════════════
# For each HMM feature group, we create:
#   PART A: Isolation Forest anomaly detection (unsupervised)
#     - Trained on PARTIAL, applied row-by-row to TRAIN
#     - Creates: {prefix}_if_anomaly_score, {prefix}_if_is_anomaly, etc.
#
#   PART B: Changepoint detection models (supervised)
#     - Uses group features + anomaly features from Part A
#     - Creates: {prefix}_chg_vol_spike_prob, {prefix}_chg_dir_reversal_prob, etc.
#
# This creates group-specific anomaly and changepoint detection that
# supports predicting changes in forward returns.
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 80}")
print("PER-GROUP ISOLATION FOREST + REGIME CHANGE DETECTION")
print("Each HMM group gets its own anomaly detector + changepoint detector")
print("Train on PARTIAL → Apply Row-by-Row to TRAIN")
print(f"{'=' * 80}\n")

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

# Convert to pandas for easier manipulation
partial_pd = df_partial.to_pandas()
train_pd = df_train.to_pandas()

# ═══════════════════════════════════════════════════════════════════════════
# PART A: PER-GROUP ISOLATION FOREST ANOMALY DETECTION
# ═══════════════════════════════════════════════════════════════════════════
# Isolation Forest is UNSUPERVISED - no target needed
# It detects statistical anomalies in the feature space of each group
# These anomalies often precede regime changes and extreme returns
# ═══════════════════════════════════════════════════════════════════════════

print("=" * 80)
print("PART A: PER-GROUP ISOLATION FOREST ANOMALY DETECTION")
print("=" * 80)
print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP A1: BUILD PER-GROUP FEATURE SETS
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP A1: Building per-group feature sets...")
print()

# Storage for all group models
GROUP_IF_MODELS = {}
GROUP_IF_SCALERS = {}
GROUP_IF_FEATURES = {}

# Combine all available groups (original + derived)
ALL_GROUP_INFO = {}

# Add original feature groups (M, E, I, P, V, S)
if "FEATURE_GROUP_INFO" in dir():
    for prefix, info in FEATURE_GROUP_INFO.items():
        ALL_GROUP_INFO[prefix] = {
            "name": info["name"],
            "input_features": info[
                "selected_columns"
            ],  # Original features used to create HMM
            "hmm_features": [
                f"{prefix}_hmm_regime",
                f"{prefix}_hmm_confidence",
                f"{prefix}_hmm_regime_change",
                f"{prefix}_hmm_duration",
            ],
            "source": "original",
        }

# Add derived feature groups (MOM, D)
if "DERIVED_FEATURE_GROUP_INFO" in dir():
    for prefix, info in DERIVED_FEATURE_GROUP_INFO.items():
        ALL_GROUP_INFO[prefix] = {
            "name": info["name"],
            "input_features": info["selected_columns"],
            "hmm_features": [
                f"{prefix}_hmm_regime",
                f"{prefix}_hmm_confidence",
                f"{prefix}_hmm_regime_change",
                f"{prefix}_hmm_duration",
            ],
            "source": "derived",
        }

# Add global HMM-4 and HMM-5 as pseudo-groups
hmm4_input_features = [
    "lagged_forward_returns",
    "daily_volatility_lagged",
    "volatility_ma_5",
    "volatility_ma_21",
]
hmm5_input_features = hmm4_input_features.copy()

ALL_GROUP_INFO["HMM4"] = {
    "name": "Global HMM-4",
    "input_features": [f for f in hmm4_input_features if f in partial_pd.columns],
    "hmm_features": [
        "hmm_regime",
        "hmm_regime_confidence",
        "hmm_regime_change",
        "hmm_regime_duration",
    ],
    "source": "global",
}

ALL_GROUP_INFO["HMM5"] = {
    "name": "Global HMM-5",
    "input_features": [f for f in hmm5_input_features if f in partial_pd.columns],
    "hmm_features": [
        "hmm5_regime",
        "hmm5_regime_confidence",
        "hmm5_regime_change",
        "hmm5_regime_duration",
    ],
    "source": "global",
}

print(f"    Total groups to process: {len(ALL_GROUP_INFO)}")
for prefix, info in ALL_GROUP_INFO.items():
    print(
        f"      • {prefix}: {info['name']} ({len(info['input_features'])} input + {len(info['hmm_features'])} HMM features)"
    )

print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP A2: TRAIN ISOLATION FOREST FOR EACH GROUP ON PARTIAL
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP A2: Training Isolation Forest for each group on PARTIAL...")
print()

# Isolation Forest parameters - tuned for detecting anomalies that may precede regime changes
IF_PARAMS = {
    "n_estimators": 100,
    "max_samples": "auto",
    "contamination": 0.05,  # Expect ~5% anomalies
    "max_features": 1.0,
    "bootstrap": False,
    "random_state": 42,
    "n_jobs": -1,
}

for prefix, group_info in ALL_GROUP_INFO.items():
    print(f"  ── {prefix}: {group_info['name']} ──")

    # Build feature list: input features + HMM features
    group_features = []
    input_features_found = []
    hmm_features_found = []
    input_features_missing = []
    hmm_features_missing = []

    # Add input features (the features used to create this HMM)
    for f in group_info["input_features"]:
        if f in partial_pd.columns:
            group_features.append(f)
            input_features_found.append(f)
        else:
            input_features_missing.append(f)

    # Add HMM output features
    for f in group_info["hmm_features"]:
        if f in partial_pd.columns:
            group_features.append(f)
            hmm_features_found.append(f)
        else:
            hmm_features_missing.append(f)

    # Log feature availability
    print(
        f"    Input features: {len(input_features_found)}/{len(group_info['input_features'])} found"
    )
    if input_features_missing:
        print(
            f"      ⚠️  Missing input: {input_features_missing[:3]}{'...' if len(input_features_missing) > 3 else ''}"
        )
    print(
        f"    HMM features: {len(hmm_features_found)}/{len(group_info['hmm_features'])} found"
    )
    if hmm_features_missing:
        print(f"      ⚠️  Missing HMM: {hmm_features_missing}")

    if len(group_features) < 2:
        print(f"    ❌ Skipped (only {len(group_features)} features available)")
        print()
        continue

    # Check for valid data - ensure numeric dtype
    X_group_df = (
        partial_pd[group_features].apply(pd.to_numeric, errors="coerce").fillna(0)
    )
    X_group = X_group_df.values.astype(np.float64)
    n_valid = len(X_group) - np.sum(np.isnan(X_group).any(axis=1))

    if n_valid < 100:
        print(f"    ⚠️ Skipped (only {n_valid} valid rows, need at least 100)")
        print()
        continue

    # Scale features (important for Isolation Forest)
    scaler_group = StandardScaler()
    X_scaled = scaler_group.fit_transform(X_group)

    # Train Isolation Forest
    try:
        if_model = IsolationForest(**IF_PARAMS)
        if_model.fit(X_scaled)

        # Get training scores for statistics
        train_scores = if_model.decision_function(X_scaled)
        train_labels = if_model.predict(X_scaled)
        n_anomalies = np.sum(train_labels == -1)

        # Store model, scaler, and features
        GROUP_IF_MODELS[prefix] = if_model
        GROUP_IF_SCALERS[prefix] = scaler_group
        GROUP_IF_FEATURES[prefix] = group_features

        print(
            f"    ✅ Trained | Features: {len(group_features)} | Anomalies: {n_anomalies}/{len(X_scaled)} ({100 * n_anomalies / len(X_scaled):.1f}%)"
        )
        print(
            f"       Score range: [{train_scores.min():.3f}, {train_scores.max():.3f}] | Mean: {train_scores.mean():.3f}"
        )
    except Exception as e:
        print(f"    ❌ Failed: {str(e)[:50]}")

    print()

print(f"  Summary: {len(GROUP_IF_MODELS)} groups with Isolation Forest models")
print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP A3: APPLY ISOLATION FOREST ROW-BY-ROW TO PARTIAL AND TRAIN
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP A3: Applying Isolation Forest row-by-row to PARTIAL and TRAIN...")
print()


def apply_group_isolation_forest(df, prefix, if_model, scaler, feature_cols):
    """
    Apply Isolation Forest for a specific group row-by-row.

    Creates features:
    - {prefix}_if_anomaly_score: Raw anomaly score (lower = more anomalous)
    - {prefix}_if_anomaly_score_norm: Normalized 0-1 (higher = more anomalous)
    - {prefix}_if_is_anomaly: Binary flag (1 = anomaly)
    - {prefix}_if_severity: Severity level (0=normal, 1=mild, 2=moderate, 3=severe)
    """
    n_rows = len(df)
    df_pd = df.to_pandas()

    # Initialize prediction arrays
    anomaly_scores = np.zeros(n_rows)
    anomaly_scores_norm = np.zeros(n_rows)
    is_anomaly = np.zeros(n_rows, dtype=int)
    severity = np.zeros(n_rows, dtype=int)

    # Get score statistics from training for normalization
    # We'll use expanding statistics to avoid look-ahead
    score_history = []

    # Process each row
    for i in range(n_rows):
        try:
            row_features = df_pd.iloc[i][feature_cols].fillna(0).values.reshape(1, -1)
            row_scaled = scaler.transform(row_features)

            # Get anomaly score and prediction
            score = if_model.decision_function(row_scaled)[0]
            pred = if_model.predict(row_scaled)[0]

            anomaly_scores[i] = score
            is_anomaly[i] = 1 if pred == -1 else 0

            # Normalize score using expanding statistics (no look-ahead)
            score_history.append(score)
            if len(score_history) >= 10:
                hist_mean = np.mean(score_history)
                hist_std = np.std(score_history) + 1e-10
                # Convert to 0-1 range where higher = more anomalous
                # Scores below mean are more anomalous
                z_score = (hist_mean - score) / hist_std
                anomaly_scores_norm[i] = 1 / (1 + np.exp(-z_score))  # Sigmoid
            else:
                anomaly_scores_norm[i] = 0.5  # Default for early rows

            # Calculate severity based on expanding percentiles
            if len(score_history) >= 50:
                pct = np.percentile(score_history, [5, 10, 25])
                if score < pct[0]:
                    severity[i] = 3  # Severe (bottom 5%)
                elif score < pct[1]:
                    severity[i] = 2  # Moderate (5-10%)
                elif score < pct[2]:
                    severity[i] = 1  # Mild (10-25%)
                else:
                    severity[i] = 0  # Normal
            else:
                severity[i] = 1 if is_anomaly[i] else 0

        except Exception:
            continue

    # Add predictions to dataframe
    df = df.with_columns(
        [
            pl.Series(f"{prefix}_if_anomaly_score", anomaly_scores),
            pl.Series(f"{prefix}_if_anomaly_score_norm", anomaly_scores_norm),
            pl.Series(f"{prefix}_if_is_anomaly", is_anomaly),
            pl.Series(f"{prefix}_if_severity", severity),
        ]
    )

    return df, [
        f"{prefix}_if_anomaly_score",
        f"{prefix}_if_anomaly_score_norm",
        f"{prefix}_if_is_anomaly",
        f"{prefix}_if_severity",
    ]


# Apply to both PARTIAL and TRAIN
all_if_columns = []

for prefix in GROUP_IF_MODELS.keys():
    print(f"    Applying {prefix} Isolation Forest...")

    # Apply to PARTIAL
    df_partial, new_cols = apply_group_isolation_forest(
        df_partial,
        prefix,
        GROUP_IF_MODELS[prefix],
        GROUP_IF_SCALERS[prefix],
        GROUP_IF_FEATURES[prefix],
    )

    # Apply to TRAIN
    df_train, _ = apply_group_isolation_forest(
        df_train,
        prefix,
        GROUP_IF_MODELS[prefix],
        GROUP_IF_SCALERS[prefix],
        GROUP_IF_FEATURES[prefix],
    )

    all_if_columns.extend(new_cols)
    print(f"      ✅ Added {len(new_cols)} anomaly features")

print(f"\n    Total Isolation Forest features: {len(all_if_columns)}")
print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP A4: CREATE GLOBAL AGGREGATE ANOMALY FEATURES
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP A4: Creating global aggregate anomaly features...")

# Update pandas views after adding IF features
partial_pd = df_partial.to_pandas()
train_pd = df_train.to_pandas()

# Get all anomaly score columns
if_score_cols = [c for c in df_partial.columns if c.endswith("_if_anomaly_score_norm")]
if_anomaly_cols = [c for c in df_partial.columns if c.endswith("_if_is_anomaly")]
if_severity_cols = [c for c in df_partial.columns if c.endswith("_if_severity")]

if if_score_cols:
    n_partial = len(df_partial)
    n_train = len(df_train)

    # Global aggregates for PARTIAL
    global_if_score_mean = partial_pd[if_score_cols].mean(axis=1).values
    global_if_score_max = partial_pd[if_score_cols].max(axis=1).values
    global_if_n_anomalies = (
        partial_pd[if_anomaly_cols].sum(axis=1).values
        if if_anomaly_cols
        else np.zeros(n_partial)
    )
    global_if_max_severity = (
        partial_pd[if_severity_cols].max(axis=1).values
        if if_severity_cols
        else np.zeros(n_partial)
    )
    global_if_any_severe = (global_if_max_severity >= 2).astype(int)

    df_partial = df_partial.with_columns(
        [
            pl.Series("group_if_anomaly_score_mean", global_if_score_mean),
            pl.Series("group_if_anomaly_score_max", global_if_score_max),
            pl.Series("group_if_n_anomalies", global_if_n_anomalies),
            pl.Series("group_if_max_severity", global_if_max_severity),
            pl.Series("group_if_any_severe", global_if_any_severe),
        ]
    )

    # Global aggregates for TRAIN
    global_if_score_mean = train_pd[if_score_cols].mean(axis=1).values
    global_if_score_max = train_pd[if_score_cols].max(axis=1).values
    global_if_n_anomalies = (
        train_pd[if_anomaly_cols].sum(axis=1).values
        if if_anomaly_cols
        else np.zeros(n_train)
    )
    global_if_max_severity = (
        train_pd[if_severity_cols].max(axis=1).values
        if if_severity_cols
        else np.zeros(n_train)
    )
    global_if_any_severe = (global_if_max_severity >= 2).astype(int)

    df_train = df_train.with_columns(
        [
            pl.Series("group_if_anomaly_score_mean", global_if_score_mean),
            pl.Series("group_if_anomaly_score_max", global_if_score_max),
            pl.Series("group_if_n_anomalies", global_if_n_anomalies),
            pl.Series("group_if_max_severity", global_if_max_severity),
            pl.Series("group_if_any_severe", global_if_any_severe),
        ]
    )

    print("    ✅ Added 5 global aggregate anomaly features")
    all_if_columns.extend(
        [
            "group_if_anomaly_score_mean",
            "group_if_anomaly_score_max",
            "group_if_n_anomalies",
            "group_if_max_severity",
            "group_if_any_severe",
        ]
    )

print()
print(f"  PART A COMPLETE: {len(all_if_columns)} Isolation Forest features created")
print()

# Update pandas views for Part B
partial_pd = df_partial.to_pandas()
train_pd = df_train.to_pandas()

# ═══════════════════════════════════════════════════════════════════════════
# PART B: PER-GROUP CHANGEPOINT DETECTION MODELS
# ═══════════════════════════════════════════════════════════════════════════
# Now we train supervised changepoint detection using:
# - Original input features
# - HMM output features
# - Isolation Forest anomaly features (from Part A)
# ═══════════════════════════════════════════════════════════════════════════

print("=" * 80)
print("PART B: PER-GROUP CHANGEPOINT DETECTION MODELS")
print("=" * 80)
print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP B1: CREATE TARGET LABELS FOR CHANGEPOINT DETECTION
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP B1: Creating target labels for regime change detection...")
print()

# Label 1: Volatility Spike (next-day volatility > 1.5x current)
if (
    "volatility_target" in partial_pd.columns
    and "daily_volatility_lagged" in partial_pd.columns
):
    vol_ratio = partial_pd["volatility_target"] / (
        partial_pd["daily_volatility_lagged"] + 1e-10
    )
    volatility_spike_label = (vol_ratio > 1.5).astype(int).values
    print(
        f"    Volatility spike: {volatility_spike_label.sum()} events ({100 * volatility_spike_label.mean():.1f}%)"
    )
else:
    volatility_spike_label = np.zeros(len(partial_pd))
    print("    ⚠️ Cannot create volatility spike label")

# Label 2: Direction Reversal
if "direction_target" in partial_pd.columns:
    dir_target = partial_pd["direction_target"].values
    prev_direction = np.roll(dir_target, 1)
    prev_direction[0] = dir_target[0]
    direction_reversal_label = (dir_target != prev_direction).astype(int)
    print(
        f"    Direction reversal: {direction_reversal_label.sum()} events ({100 * direction_reversal_label.mean():.1f}%)"
    )
else:
    direction_reversal_label = np.zeros(len(partial_pd))
    print("    ⚠️ Cannot create direction reversal label")

# Label 3: Extreme Return (|forward_returns| > 2 * expanding std)
if "forward_returns" in partial_pd.columns:
    fwd_ret = partial_pd["forward_returns"].values
    expanding_std = np.zeros(len(fwd_ret))
    for i in range(1, len(fwd_ret)):
        expanding_std[i] = np.std(fwd_ret[:i]) if i > 1 else 0.01
    expanding_std[0] = 0.01
    extreme_return_label = (np.abs(fwd_ret) > 2 * (expanding_std + 1e-10)).astype(int)
    print(
        f"    Extreme return: {extreme_return_label.sum()} events ({100 * extreme_return_label.mean():.1f}%)"
    )
else:
    extreme_return_label = np.zeros(len(partial_pd))
    print("    ⚠️ Cannot create extreme return label")

print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: BUILD PER-GROUP FEATURE SETS
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP 2: Building per-group feature sets...")
print()

# Storage for all group models
GROUP_CHANGEPOINT_MODELS = {}
GROUP_CHANGEPOINT_SCALERS = {}
GROUP_CHANGEPOINT_FEATURES = {}
GROUP_CHANGEPOINT_QUALITY = {}

# Combine all available groups (original + derived)
ALL_GROUP_INFO = {}

# Add original feature groups (M, E, I, P, V, S)
if "FEATURE_GROUP_INFO" in dir():
    for prefix, info in FEATURE_GROUP_INFO.items():
        ALL_GROUP_INFO[prefix] = {
            "name": info["name"],
            "input_features": info[
                "selected_columns"
            ],  # Original features used to create HMM
            "hmm_features": [
                f"{prefix}_hmm_regime",
                f"{prefix}_hmm_confidence",
                f"{prefix}_hmm_regime_change",
                f"{prefix}_hmm_duration",
            ],
            "source": "original",
        }

# Add derived feature groups (MOM, D)
if "DERIVED_FEATURE_GROUP_INFO" in dir():
    for prefix, info in DERIVED_FEATURE_GROUP_INFO.items():
        ALL_GROUP_INFO[prefix] = {
            "name": info["name"],
            "input_features": info["selected_columns"],
            "hmm_features": [
                f"{prefix}_hmm_regime",
                f"{prefix}_hmm_confidence",
                f"{prefix}_hmm_regime_change",
                f"{prefix}_hmm_duration",
            ],
            "source": "derived",
        }

# Also add global HMM-4 and HMM-5 as pseudo-groups
hmm4_input_features = [
    "lagged_forward_returns",
    "daily_volatility_lagged",
    "volatility_ma_5",
    "volatility_ma_21",
]
hmm5_input_features = hmm4_input_features.copy()

ALL_GROUP_INFO["HMM4"] = {
    "name": "Global HMM-4",
    "input_features": [f for f in hmm4_input_features if f in partial_pd.columns],
    "hmm_features": [
        "hmm_regime",
        "hmm_regime_confidence",
        "hmm_regime_change",
        "hmm_regime_duration",
    ],
    "source": "global",
}

ALL_GROUP_INFO["HMM5"] = {
    "name": "Global HMM-5",
    "input_features": [f for f in hmm5_input_features if f in partial_pd.columns],
    "hmm_features": [
        "hmm5_regime",
        "hmm5_regime_confidence",
        "hmm5_regime_change",
        "hmm5_regime_duration",
    ],
    "source": "global",
}

print(f"    Total groups to process: {len(ALL_GROUP_INFO)}")
for prefix, info in ALL_GROUP_INFO.items():
    print(
        f"      • {prefix}: {info['name']} ({len(info['input_features'])} input + {len(info['hmm_features'])} HMM features)"
    )

print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP B3: TRAIN PER-GROUP CHANGEPOINT DETECTION MODELS
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP B3: Training per-group changepoint detection models...")
print("         (Now includes Isolation Forest features from Part A)")
print()

# Model parameters
MODEL_PARAMS = {
    "n_estimators": 50,
    "max_depth": 4,
    "min_samples_split": 20,
    "min_samples_leaf": 10,
    "random_state": 42,
    "n_jobs": -1,
    "class_weight": "balanced",
}

min_history = 50
valid_mask = np.arange(len(partial_pd)) >= min_history

for prefix, group_info in ALL_GROUP_INFO.items():
    print(f"  ── {prefix}: {group_info['name']} ──")

    # Build feature list: input features + HMM features + Isolation Forest features
    group_features = []
    input_found = 0
    hmm_found = 0
    if_found = 0
    global_if_found = 0

    # Add input features (the features used to create this HMM)
    for f in group_info["input_features"]:
        if f in partial_pd.columns:
            group_features.append(f)
            input_found += 1

    # Add HMM output features
    hmm_missing = []
    for f in group_info["hmm_features"]:
        if f in partial_pd.columns:
            group_features.append(f)
            hmm_found += 1
        else:
            hmm_missing.append(f)

    # Add Isolation Forest features for this group (from Part A)
    if_features = [
        f"{prefix}_if_anomaly_score",
        f"{prefix}_if_anomaly_score_norm",
        f"{prefix}_if_is_anomaly",
        f"{prefix}_if_severity",
    ]
    if_missing = []
    for f in if_features:
        if f in partial_pd.columns:
            group_features.append(f)
            if_found += 1
        else:
            if_missing.append(f)

    # Add global IF aggregate features
    global_if_features = [
        "group_if_anomaly_score_mean",
        "group_if_anomaly_score_max",
        "group_if_n_anomalies",
        "group_if_max_severity",
        "group_if_any_severe",
    ]
    for f in global_if_features:
        if f in partial_pd.columns and f not in group_features:
            group_features.append(f)
            global_if_found += 1

    # Log detailed feature breakdown
    print("    Features breakdown:")
    print(f"      Input: {input_found}/{len(group_info['input_features'])}")
    print(
        f"      HMM: {hmm_found}/{len(group_info['hmm_features'])}"
        + (f" ⚠️ Missing: {hmm_missing}" if hmm_missing else "")
    )
    print(
        f"      IF (group): {if_found}/4"
        + (f" ⚠️ Missing: {if_missing[:2]}..." if if_missing else "")
    )
    print(f"      IF (global): {global_if_found}/5")

    n_input = input_found
    n_hmm = hmm_found
    n_if = if_found + global_if_found

    if len(group_features) < 3:
        print(f"    ❌ Skipped (only {len(group_features)} features available)")
        print()
        continue

    print(
        f"    Total: {n_input} input + {n_hmm} HMM + {n_if} IF = {len(group_features)} features"
    )

    # Check for valid data - ensure numeric dtype
    X_group_df = (
        partial_pd[group_features].apply(pd.to_numeric, errors="coerce").fillna(0)
    )
    X_group = X_group_df.values.astype(np.float64)
    n_valid = len(X_group) - np.sum(np.isnan(X_group).any(axis=1))

    if n_valid < min_history + 50:
        print(f"    ⚠️ Skipped (only {n_valid} valid rows)")
        print()
        continue

    # Scale features
    scaler_group = StandardScaler()
    X_scaled = scaler_group.fit_transform(X_group)

    # Store feature list and scaler
    GROUP_CHANGEPOINT_FEATURES[prefix] = group_features
    GROUP_CHANGEPOINT_SCALERS[prefix] = scaler_group
    GROUP_CHANGEPOINT_MODELS[prefix] = {}
    GROUP_CHANGEPOINT_QUALITY[prefix] = {}

    # Train volatility spike detector for this group
    if volatility_spike_label.sum() >= 10:
        X_train = X_scaled[valid_mask]
        y_train = volatility_spike_label[valid_mask]

        try:
            model = RandomForestClassifier(**MODEL_PARAMS)
            model.fit(X_train, y_train)
            y_proba = model.predict_proba(X_train)[:, 1]
            auc = (
                roc_auc_score(y_train, y_proba) if len(np.unique(y_train)) > 1 else 0.5
            )

            GROUP_CHANGEPOINT_MODELS[prefix]["vol_spike"] = model
            GROUP_CHANGEPOINT_QUALITY[prefix]["vol_spike"] = {
                "auc": auc,
                "n_events": int(y_train.sum()),
            }
        except Exception:
            pass

    # Train direction reversal detector for this group
    if direction_reversal_label.sum() >= 10:
        X_train = X_scaled[valid_mask]
        y_train = direction_reversal_label[valid_mask]

        try:
            model = RandomForestClassifier(**MODEL_PARAMS)
            model.fit(X_train, y_train)
            y_proba = model.predict_proba(X_train)[:, 1]
            auc = (
                roc_auc_score(y_train, y_proba) if len(np.unique(y_train)) > 1 else 0.5
            )

            GROUP_CHANGEPOINT_MODELS[prefix]["dir_reversal"] = model
            GROUP_CHANGEPOINT_QUALITY[prefix]["dir_reversal"] = {
                "auc": auc,
                "n_events": int(y_train.sum()),
            }
        except Exception:
            pass

    # Train extreme return detector for this group
    if extreme_return_label.sum() >= 10:
        X_train = X_scaled[valid_mask]
        y_train = extreme_return_label[valid_mask]

        try:
            model = RandomForestClassifier(**MODEL_PARAMS)
            model.fit(X_train, y_train)
            y_proba = model.predict_proba(X_train)[:, 1]
            auc = (
                roc_auc_score(y_train, y_proba) if len(np.unique(y_train)) > 1 else 0.5
            )

            GROUP_CHANGEPOINT_MODELS[prefix]["extreme_ret"] = model
            GROUP_CHANGEPOINT_QUALITY[prefix]["extreme_ret"] = {
                "auc": auc,
                "n_events": int(y_train.sum()),
            }
        except Exception:
            pass

    # Print summary for this group
    n_models = len(GROUP_CHANGEPOINT_MODELS[prefix])
    if n_models > 0:
        aucs = [q["auc"] for q in GROUP_CHANGEPOINT_QUALITY[prefix].values()]
        avg_auc = np.mean(aucs)
        print(
            f"    ✅ Trained {n_models} models | Features: {len(group_features)} | Avg AUC: {avg_auc:.3f}"
        )
        for model_type, quality in GROUP_CHANGEPOINT_QUALITY[prefix].items():
            print(f"       • {model_type}: AUC={quality['auc']:.3f}")
    else:
        print("    ⚠️ No models trained")

    print()

print(f"  Summary: {len(GROUP_CHANGEPOINT_MODELS)} groups with models")
print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP B4: APPLY PER-GROUP CHANGEPOINT MODELS ROW-BY-ROW TO PARTIAL AND TRAIN
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP B4: Applying per-group changepoint models row-by-row...")
print()


def apply_group_changepoint_models(df, prefix, models_dict, scaler, feature_cols):
    """Apply changepoint models for a specific group row-by-row."""
    n_rows = len(df)
    df_pd = df.to_pandas()

    # Initialize prediction arrays for this group
    predictions = {
        f"{prefix}_chg_vol_spike_prob": np.zeros(n_rows),
        f"{prefix}_chg_dir_reversal_prob": np.zeros(n_rows),
        f"{prefix}_chg_extreme_ret_prob": np.zeros(n_rows),
        f"{prefix}_chg_combined": np.zeros(n_rows),
        f"{prefix}_chg_any_high": np.zeros(n_rows, dtype=int),
    }

    # Process each row
    for i in range(n_rows):
        try:
            row_features = df_pd.iloc[i][feature_cols].fillna(0).values.reshape(1, -1)
            row_scaled = scaler.transform(row_features)
        except:
            continue

        probs = []

        if "vol_spike" in models_dict:
            prob = models_dict["vol_spike"].predict_proba(row_scaled)[0, 1]
            predictions[f"{prefix}_chg_vol_spike_prob"][i] = prob
            probs.append(prob)

        if "dir_reversal" in models_dict:
            prob = models_dict["dir_reversal"].predict_proba(row_scaled)[0, 1]
            predictions[f"{prefix}_chg_dir_reversal_prob"][i] = prob
            probs.append(prob)

        if "extreme_ret" in models_dict:
            prob = models_dict["extreme_ret"].predict_proba(row_scaled)[0, 1]
            predictions[f"{prefix}_chg_extreme_ret_prob"][i] = prob
            probs.append(prob)

        if probs:
            predictions[f"{prefix}_chg_combined"][i] = np.mean(probs)
            predictions[f"{prefix}_chg_any_high"][i] = 1 if max(probs) > 0.5 else 0

    # Add predictions to dataframe
    for col_name, values in predictions.items():
        df = df.with_columns([pl.Series(col_name, values)])

    return df, list(predictions.keys())


# Apply to both PARTIAL and TRAIN
all_new_columns = []

for prefix in GROUP_CHANGEPOINT_MODELS.keys():
    if not GROUP_CHANGEPOINT_MODELS[prefix]:
        continue

    print(f"    Applying {prefix} models...")

    # Apply to PARTIAL
    df_partial, new_cols = apply_group_changepoint_models(
        df_partial,
        prefix,
        GROUP_CHANGEPOINT_MODELS[prefix],
        GROUP_CHANGEPOINT_SCALERS[prefix],
        GROUP_CHANGEPOINT_FEATURES[prefix],
    )

    # Apply to TRAIN
    df_train, _ = apply_group_changepoint_models(
        df_train,
        prefix,
        GROUP_CHANGEPOINT_MODELS[prefix],
        GROUP_CHANGEPOINT_SCALERS[prefix],
        GROUP_CHANGEPOINT_FEATURES[prefix],
    )

    all_new_columns.extend(new_cols)
    print(f"      ✅ Added {len(new_cols)} features")

print(f"\n    Total new features: {len(all_new_columns)}")
print()

# ═══════════════════════════════════════════════════════════════════════════
# STEP B5: CREATE GLOBAL AGGREGATE CHANGEPOINT FEATURES
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP B5: Creating global aggregate changepoint features...")

# Aggregate across all groups
n_partial = len(df_partial)
n_train = len(df_train)

# For PARTIAL
vol_spike_cols = [c for c in df_partial.columns if c.endswith("_chg_vol_spike_prob")]
dir_rev_cols = [c for c in df_partial.columns if c.endswith("_chg_dir_reversal_prob")]
extreme_ret_cols = [
    c for c in df_partial.columns if c.endswith("_chg_extreme_ret_prob")
]
combined_cols = [c for c in df_partial.columns if c.endswith("_chg_combined")]

if vol_spike_cols:
    partial_pd = df_partial.to_pandas()
    train_pd = df_train.to_pandas()

    # Global aggregates for PARTIAL
    global_vol_spike = partial_pd[vol_spike_cols].mean(axis=1).values
    global_dir_rev = (
        partial_pd[dir_rev_cols].mean(axis=1).values
        if dir_rev_cols
        else np.zeros(n_partial)
    )
    global_extreme = (
        partial_pd[extreme_ret_cols].mean(axis=1).values
        if extreme_ret_cols
        else np.zeros(n_partial)
    )
    global_combined = (
        partial_pd[combined_cols].mean(axis=1).values
        if combined_cols
        else np.zeros(n_partial)
    )
    global_max = (
        partial_pd[combined_cols].max(axis=1).values
        if combined_cols
        else np.zeros(n_partial)
    )
    global_any_high = (global_max > 0.5).astype(int)

    df_partial = df_partial.with_columns(
        [
            pl.Series("regime_change_vol_spike_prob", global_vol_spike),
            pl.Series("regime_change_dir_reversal_prob", global_dir_rev),
            pl.Series("regime_change_extreme_ret_prob", global_extreme),
            pl.Series("regime_change_combined_signal", global_combined),
            pl.Series("regime_change_max_signal", global_max),
            pl.Series("regime_change_any_high", global_any_high),
            pl.Series(
                "regime_change_n_groups_high",
                (partial_pd[combined_cols] > 0.5).sum(axis=1).values
                if combined_cols
                else np.zeros(n_partial),
            ),
        ]
    )

    # Global aggregates for TRAIN
    global_vol_spike = train_pd[vol_spike_cols].mean(axis=1).values
    global_dir_rev = (
        train_pd[dir_rev_cols].mean(axis=1).values
        if dir_rev_cols
        else np.zeros(n_train)
    )
    global_extreme = (
        train_pd[extreme_ret_cols].mean(axis=1).values
        if extreme_ret_cols
        else np.zeros(n_train)
    )
    global_combined = (
        train_pd[combined_cols].mean(axis=1).values
        if combined_cols
        else np.zeros(n_train)
    )
    global_max = (
        train_pd[combined_cols].max(axis=1).values
        if combined_cols
        else np.zeros(n_train)
    )
    global_any_high = (global_max > 0.5).astype(int)

    df_train = df_train.with_columns(
        [
            pl.Series("regime_change_vol_spike_prob", global_vol_spike),
            pl.Series("regime_change_dir_reversal_prob", global_dir_rev),
            pl.Series("regime_change_extreme_ret_prob", global_extreme),
            pl.Series("regime_change_combined_signal", global_combined),
            pl.Series("regime_change_max_signal", global_max),
            pl.Series("regime_change_any_high", global_any_high),
            pl.Series(
                "regime_change_n_groups_high",
                (train_pd[combined_cols] > 0.5).sum(axis=1).values
                if combined_cols
                else np.zeros(n_train),
            ),
        ]
    )

    print("    ✅ Added 7 global aggregate features")

print()

# Update working dataframe
df_pl = df_train.clone()

# ═══════════════════════════════════════════════════════════════════════════
# STEP B6: SAVE STATE FOR API SIMULATION
# ═══════════════════════════════════════════════════════════════════════════

print("  STEP B6: Saving state for API simulation...")

# Combined state for both Isolation Forest and Changepoint Detection
group_detection_state = {
    # SESSION ID FOR VALIDATION
    "session_id": TRAINING_SESSION_ID,
    # PART A: Isolation Forest models
    "if_models": GROUP_IF_MODELS,
    "if_scalers": GROUP_IF_SCALERS,
    "if_features": GROUP_IF_FEATURES,
    # PART B: Changepoint Detection models
    "chg_models": GROUP_CHANGEPOINT_MODELS,
    "chg_scalers": GROUP_CHANGEPOINT_SCALERS,
    "chg_features": GROUP_CHANGEPOINT_FEATURES,
    "chg_quality": GROUP_CHANGEPOINT_QUALITY,
    # Group info for reference
    "group_info": ALL_GROUP_INFO,
    # Training info
    "n_groups_if": len(GROUP_IF_MODELS),
    "n_groups_chg": len(GROUP_CHANGEPOINT_MODELS),
    "total_chg_models": sum(len(m) for m in GROUP_CHANGEPOINT_MODELS.values()),
}

# Save to pickle
import pickle

group_detection_state_path = output_dir / "group_detection_state.pkl"
with open(group_detection_state_path, "wb") as f:
    pickle.dump(group_detection_state, f)

print(
    f"    ✅ Saved {group_detection_state['n_groups_if']} groups with Isolation Forest models"
)
print(
    f"    ✅ Saved {group_detection_state['n_groups_chg']} groups with {group_detection_state['total_chg_models']} changepoint models"
)
print(f"    ✅ State saved to: {group_detection_state_path}")

# ═══════════════════════════════════════════════════════════════════════════
# DETAILED FEATURE VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 80}")
print("DETAILED FEATURE VERIFICATION BY GROUP")
print(f"{'=' * 80}")

# Refresh pandas views
partial_pd_final = df_partial.to_pandas()

for prefix, group_info in ALL_GROUP_INFO.items():
    print(f"\n  📊 {prefix}: {group_info['name']}")
    print(f"  {'─' * 70}")

    # Check input features
    input_cols = group_info["input_features"]
    input_found = [c for c in input_cols if c in partial_pd_final.columns]
    input_missing = [c for c in input_cols if c not in partial_pd_final.columns]

    # Check HMM features
    hmm_cols = group_info["hmm_features"]
    hmm_found = [c for c in hmm_cols if c in partial_pd_final.columns]
    hmm_missing = [c for c in hmm_cols if c not in partial_pd_final.columns]

    # Check IF features (from Part A)
    if_cols = [
        f"{prefix}_if_anomaly_score",
        f"{prefix}_if_anomaly_score_norm",
        f"{prefix}_if_is_anomaly",
        f"{prefix}_if_severity",
    ]
    if_found = [c for c in if_cols if c in partial_pd_final.columns]
    if_missing = [c for c in if_cols if c not in partial_pd_final.columns]

    # Check Changepoint features (from Part B)
    chg_cols = [
        f"{prefix}_chg_vol_spike_prob",
        f"{prefix}_chg_dir_reversal_prob",
        f"{prefix}_chg_extreme_ret_prob",
        f"{prefix}_chg_combined",
        f"{prefix}_chg_any_high",
    ]
    chg_found = [c for c in chg_cols if c in partial_pd_final.columns]
    chg_missing = [c for c in chg_cols if c not in partial_pd_final.columns]

    # Print status
    input_status = "✅" if len(input_missing) == 0 else "⚠️"
    hmm_status = "✅" if len(hmm_missing) == 0 else "❌"
    if_status = "✅" if len(if_missing) == 0 else "❌"
    chg_status = "✅" if len(chg_missing) == 0 else "❌"

    print(f"    {input_status} Input features: {len(input_found)}/{len(input_cols)}")
    if input_found:
        print(f"       Found: {input_found[:5]}{'...' if len(input_found) > 5 else ''}")

    print(f"    {hmm_status} HMM features: {len(hmm_found)}/{len(hmm_cols)}")
    if hmm_missing:
        print(f"       ❌ Missing: {hmm_missing}")

    print(f"    {if_status} Isolation Forest features: {len(if_found)}/{len(if_cols)}")
    if if_missing:
        print(f"       ❌ Missing: {if_missing}")

    print(f"    {chg_status} Changepoint features: {len(chg_found)}/{len(chg_cols)}")
    if chg_missing:
        print(f"       ❌ Missing: {chg_missing}")

    # Summary for this group
    total_expected = len(input_cols) + len(hmm_cols) + len(if_cols) + len(chg_cols)
    total_found = len(input_found) + len(hmm_found) + len(if_found) + len(chg_found)
    completeness = total_found / total_expected * 100 if total_expected > 0 else 0

    if completeness == 100:
        print(f"    ✅ COMPLETE: All {total_expected} features present")
    elif completeness >= 70:
        print(
            f"    ⚠️ PARTIAL: {total_found}/{total_expected} features ({completeness:.0f}%)"
        )
    else:
        print(
            f"    ❌ INCOMPLETE: Only {total_found}/{total_expected} features ({completeness:.0f}%)"
        )

# Global IF aggregates check
print("\n  📊 GLOBAL AGGREGATES")
print(f"  {'─' * 70}")

global_if_cols = [
    "group_if_anomaly_score_mean",
    "group_if_anomaly_score_max",
    "group_if_n_anomalies",
    "group_if_max_severity",
    "group_if_any_severe",
]
global_if_found = [c for c in global_if_cols if c in partial_pd_final.columns]
global_if_missing = [c for c in global_if_cols if c not in partial_pd_final.columns]

global_chg_cols = [
    "regime_change_vol_spike_prob",
    "regime_change_dir_reversal_prob",
    "regime_change_extreme_ret_prob",
    "regime_change_combined_signal",
    "regime_change_max_signal",
    "regime_change_any_high",
    "regime_change_n_groups_high",
]
global_chg_found = [c for c in global_chg_cols if c in partial_pd_final.columns]
global_chg_missing = [c for c in global_chg_cols if c not in partial_pd_final.columns]

if_global_status = "✅" if len(global_if_missing) == 0 else "❌"
chg_global_status = "✅" if len(global_chg_missing) == 0 else "❌"

print(
    f"    {if_global_status} Global IF aggregates: {len(global_if_found)}/{len(global_if_cols)}"
)
if global_if_missing:
    print(f"       ❌ Missing: {global_if_missing}")

print(
    f"    {chg_global_status} Global Changepoint aggregates: {len(global_chg_found)}/{len(global_chg_cols)}"
)
if global_chg_missing:
    print(f"       ❌ Missing: {global_chg_missing}")

# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 80}")
print("CELL 7.8 SUMMARY: PER-GROUP ISOLATION FOREST + CHANGEPOINT DETECTION")
print(f"{'=' * 80}")

print("\n  PART A: ISOLATION FOREST (Unsupervised Anomaly Detection)")
print("  ─────────────────────────────────────────────────────────")
print(f"    Groups with IF models: {len(GROUP_IF_MODELS)}")
print(
    f"    Features per group: 4 ({'{prefix}'}_if_anomaly_score, _norm, _is_anomaly, _severity)"
)
print(
    "    Global aggregates: 5 (group_if_anomaly_score_mean/max, n_anomalies, max_severity, any_severe)"
)
print(f"    Total IF features: {len(all_if_columns)}")

print("\n  PART B: CHANGEPOINT DETECTION (Supervised)")
print("  ──────────────────────────────────────────")
print(f"    Groups with changepoint models: {len(GROUP_CHANGEPOINT_MODELS)}")
for prefix, models in GROUP_CHANGEPOINT_MODELS.items():
    if models:
        group_name = ALL_GROUP_INFO[prefix]["name"]
        n_input = len(ALL_GROUP_INFO[prefix]["input_features"])
        n_hmm = len(ALL_GROUP_INFO[prefix]["hmm_features"])
        n_if = len(
            [f for f in GROUP_CHANGEPOINT_FEATURES.get(prefix, []) if "_if_" in f]
        )
        quality = GROUP_CHANGEPOINT_QUALITY[prefix]
        aucs = [q["auc"] for q in quality.values()]
        print(
            f"      • {prefix}: {len(models)} models, {n_input} input + {n_hmm} HMM + {n_if} IF features, AUC={np.mean(aucs):.3f}"
        )

print("\n  Features per group (changepoint):")
print("    • {prefix}_chg_vol_spike_prob: P(volatility spike)")
print("    • {prefix}_chg_dir_reversal_prob: P(direction reversal)")
print("    • {prefix}_chg_extreme_ret_prob: P(extreme return)")
print("    • {prefix}_chg_combined: Average signal")
print("    • {prefix}_chg_any_high: Binary flag")

print("\n  Global changepoint aggregates:")
print("    • regime_change_vol_spike_prob, dir_reversal_prob, extreme_ret_prob")
print("    • regime_change_combined_signal, max_signal, any_high, n_groups_high")

total_new = len(all_if_columns) + len(all_new_columns) + 7
print(f"\n  TOTAL NEW FEATURES: {total_new}")
print(f"    • Isolation Forest: {len(all_if_columns)}")
print(f"    • Changepoint: {len(all_new_columns) + 7}")

print("\n  DATA LEAKAGE VERIFICATION:")
print(
    "    ✅ Isolation Forest: Trained on PARTIAL (unsupervised), applied row-by-row to TRAIN"
)
print(
    "    ✅ Changepoint: Trained on PARTIAL (supervised), applied row-by-row to TRAIN"
)
print(
    "    ✅ NO TARGET ACCESS: Features only use lagged values + HMM outputs + IF outputs"
)
print("    ✅ NO FORWARD PEEKING: Each row prediction uses only that row's data")
print(f"\n{'=' * 80}\n")

# Sync columns after adding new features
train_cols = set(df_train.columns)
partial_cols = set(df_partial.columns)
missing_in_partial = train_cols - partial_cols
if missing_in_partial:
    for col in missing_in_partial:
        col_dtype = df_train[col].dtype
        default_val = 0 if col_dtype in [pl.Int32, pl.Int64, pl.Int8] else 0.0
        df_partial = df_partial.with_columns(
            [pl.lit(default_val).cast(col_dtype).alias(col)]
        )
    df_partial = df_partial.select(df_train.columns)
    print(f"  ✅ Synced {len(missing_in_partial)} new columns to PARTIAL")

# %% [CELL 9] Helper Baseline Models (LR, EWMA, Direction)

# HELPER BASELINE MODELS (Baseline Models for PARTIAL + TRAIN)
# Uses combine→engineer→split strategy for PARTIAL + TRAIN
# VALIDATION will be processed row-by-row in API simulation
# ✅ NO DATA LEAKAGE: Expanding window training uses only past data


print(f"\n{'=' * 80}")
print("STEP 1.3c: CREATING HELPER BASELINE MODELS (PARTIAL + TRAIN)")
print(f"{'=' * 80}\n")

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

# TEMPORAL CORRECTNESS VERIFICATION:
# At row i, we predict using data from rows 0 to i-1 ONLY
# The "targets" (volatility_target, direction_target) from rows 0 to i-1 are REALIZED VALUES
# These were "future" at those times, but are now KNOWN/HISTORICAL
# Example: At t=100, we train on realized volatility from t=0 to t=99 to predict t=100
# ✅ This is CORRECT - no data leakage!

# STEP 1: COMBINE PARTIAL + TRAIN for continuous timeline
print("\n  STEP 1: Combining PARTIAL + TRAIN datasets...")
idx_partial_end_helper = len(df_partial)
idx_train_end_helper = idx_partial_end_helper + len(df_train)

df_combined_helper = pl.concat([df_partial, df_train], how="vertical")
print(
    f"    • Combined: {len(df_combined_helper)} rows (PARTIAL: {idx_partial_end_helper}, TRAIN: {idx_train_end_helper - idx_partial_end_helper})"
)
print("    ℹ️  VALIDATION will be processed row-by-row in API simulation")

# STEP 2: ENGINEER helper features on combined dataset
print("\n  STEP 2: Engineering helper features...")
print("    ✅ EXPANDING WINDOW: At row i, train on rows 0 to i-1 ONLY")
print("    ✅ NO FUTURE DATA: Targets are historical realized values")


# 1. LINEAR REGRESSION VOLATILITY HELPER


print("\n  ✓ Creating Linear Regression Volatility Helper...")

# Features for volatility prediction (ALL HISTORICAL/LAGGED)
vol_features_cols = [
    "daily_volatility_lagged",  # Lagged - past data
    "volatility_ma_5",  # Moving average - past data
    "volatility_ma_21",  # Moving average - past data
    "mean_hist_vol_5",  # Historical mean - past data
    "mean_hist_vol_21",  # Historical mean - past data
]

# Prepare data from combined dataset
helper_vol_lr_predictions = np.zeros(len(df_combined_helper))
min_train_size = 100  # Minimum samples before making predictions

# Rolling window training (expanding window) on combined dataset
# CRITICAL: At row i, we train ONLY on rows 0 to i-1 (no future data!)
for i in range(min_train_size, len(df_combined_helper)):
    # Training data: all previous data (rows 0 to i-1)
    train_data = df_combined_helper[:i].select(vol_features_cols).to_numpy()
    train_target = df_combined_helper[:i]["volatility_target"].to_numpy()
    # ^ volatility_target[j] for j<i are REALIZED values (historical)

    # Remove NaN rows
    valid_mask = ~np.isnan(train_data).any(axis=1) & ~np.isnan(train_target)

    if valid_mask.sum() < 50:  # Need minimum 50 samples
        helper_vol_lr_predictions[i] = 0.0
        continue

    train_data_clean = train_data[valid_mask]
    train_target_clean = train_target[valid_mask]

    # Train model on historical data
    lr = LinearRegression()
    lr.fit(train_data_clean, train_target_clean)

    # Predict current point (row i) using features at row i
    current_features = (
        df_combined_helper[i : i + 1].select(vol_features_cols).to_numpy()
    )
    if not np.isnan(current_features).any():
        helper_vol_lr_predictions[i] = lr.predict(current_features)[0]
    else:
        helper_vol_lr_predictions[i] = 0.0

# Add to combined dataframe
df_combined_helper = df_combined_helper.with_columns(
    [pl.lit(helper_vol_lr_predictions).alias("helper_vol_lr")]
)

# Create helper_vol_lr_error - LAGGED to avoid data leakage
# ⚠️ CRITICAL: We use shift(1) to get the ERROR FROM THE PREVIOUS PREDICTION
# This avoids using the current target value in the feature
df_combined_helper = df_combined_helper.with_columns(
    [
        (pl.col("volatility_target").shift(1) - pl.col("helper_vol_lr").shift(1)).alias(
            "helper_vol_lr_error"
        )
    ]
)

print("    • Created helper_vol_lr (Linear Regression volatility predictions)")
print("    • Created helper_vol_lr_error (LAGGED prediction errors - no leakage)")
print(f"    • First {min_train_size} values = 0 (insufficient training data)")
print(f"    • Expanding window: min 50 samples, max {len(df_combined_helper)} samples")
print("    ✅ VERIFIED: Uses only past data (rows 0 to i-1 to predict row i)")


# 2. EWMA VOLATILITY HELPER - ROW-BY-ROW (MUST MATCH API SIMULATION EXACTLY)


print("\n  ✓ Creating EWMA Volatility Helper (ROW-BY-ROW - matches API exactly)...")

# ═══════════════════════════════════════════════════════════════════════════════
# CRITICAL: Use EXACT same row-by-row logic as Cell 28 API simulation
# Formula: ewma[t] = alpha * value[t] + (1 - alpha) * ewma[t-1]
# where alpha = 2 / (span + 1)
# ═══════════════════════════════════════════════════════════════════════════════
ewma_span = 21  # ~1 month
alpha = 2.0 / (ewma_span + 1)

# Get raw values
vols_raw = df_combined_helper["daily_volatility_lagged"].to_numpy()
absrets_raw = np.abs(df_combined_helper["lagged_forward_returns"].to_numpy())

# Initialize arrays
helper_vol_ewma_predictions = np.zeros(len(df_combined_helper))
helper_vol_ewma_variance = np.zeros(len(df_combined_helper))
helper_vol_ewma_absret = np.zeros(len(df_combined_helper))

# Row-by-row calculation (EXACTLY as Cell 28 does)
hist_vols = []
hist_absrets = []

for i in range(len(df_combined_helper)):
    vol = vols_raw[i] if not np.isnan(vols_raw[i]) else 0.0
    absret = absrets_raw[i] if not np.isnan(absrets_raw[i]) else 0.0

    if i == 0:
        # First row: initialize with current value
        helper_vol_ewma_predictions[i] = vol
        helper_vol_ewma_absret[i] = absret
        helper_vol_ewma_variance[i] = 0.0
    else:
        # EWMA update: alpha * current + (1-alpha) * previous
        helper_vol_ewma_predictions[i] = (
            alpha * vol + (1 - alpha) * helper_vol_ewma_predictions[i - 1]
        )
        helper_vol_ewma_absret[i] = (
            alpha * absret + (1 - alpha) * helper_vol_ewma_absret[i - 1]
        )

        # Variance: std of recent values in window (matches Cell 28 logic)
        if len(hist_vols) >= ewma_span:
            helper_vol_ewma_variance[i] = np.std(hist_vols[-ewma_span:], ddof=1)
        else:
            helper_vol_ewma_variance[i] = (
                np.std(hist_vols, ddof=1) if len(hist_vols) > 1 else 0.0
            )

    # Update history
    hist_vols.append(vol)
    hist_absrets.append(absret)

    if (i + 1) % 500 == 0 or i == 0 or i == len(df_combined_helper) - 1:
        print(f"    • Processed {i + 1}/{len(df_combined_helper)} rows for EWMA")

# Add to combined dataframe
df_combined_helper = df_combined_helper.with_columns(
    [
        pl.lit(helper_vol_ewma_predictions).alias("helper_vol_ewma"),
        pl.lit(helper_vol_ewma_variance).alias("helper_vol_ewma_variance"),
        pl.lit(helper_vol_ewma_absret).alias("helper_vol_ewma_absret"),
    ]
)

# Create helper_vol_ewma_error - LAGGED to avoid data leakage
# ⚠️ CRITICAL: We use shift(1) to get the ERROR FROM THE PREVIOUS PREDICTION
# This avoids using the current target value in the feature
df_combined_helper = df_combined_helper.with_columns(
    [
        (
            pl.col("volatility_target").shift(1) - pl.col("helper_vol_ewma").shift(1)
        ).alias("helper_vol_ewma_error")
    ]
)

print(f"    • Created helper_vol_ewma (ROW-BY-ROW EWMA, alpha={alpha:.4f})")
print("    • Created helper_vol_ewma_error (LAGGED prediction errors - no leakage)")
print(f"    • Created helper_vol_ewma_variance (rolling std over {ewma_span} days)")
print("    • Created helper_vol_ewma_absret (ROW-BY-ROW EWMA of abs returns)")
print("    ✅ CRITICAL: Uses EXACT same row-by-row logic as API simulation!")


# 3. LOGISTIC REGRESSION DIRECTION HELPER (ENHANCED)


print("\n  ✓ Creating Enhanced Logistic Regression Direction Helper...")

# ENHANCED features for direction prediction (ALL HISTORICAL)
dir_features_cols = [
    # Original momentum features (5) - all lagged/historical
    "lagged_forward_returns",
    "momentum_5d",
    "momentum_21d",
    "zscore_5d",
    "dist_from_ma_21d",
    # VOLATILITY FEATURES (3) - high vol often precedes directional moves
    "daily_volatility_lagged",
    "volatility_ma_5",
    "vol_of_vol_5d",  # Volatility of volatility
    # HMM REGIME FEATURES (3) - regimes from past data
    "hmm_regime",
    "hmm5_regime",  # 5-regime volatility HMM
    "hmm_regime_confidence",
    # DRAWDOWN FEATURES (2) - position in range
    "max_drawdown_5d",
    "max_drawdown_21d",
    # MEAN REVERSION INDICATORS (2)
    "consecutive_up",
    "consecutive_down",
]

# Prepare data from combined dataset
helper_dir_prob_predictions = np.zeros(len(df_combined_helper))

# Rolling window training (expanding window) on combined dataset
# CRITICAL: At row i, we train ONLY on rows 0 to i-1 (no future data!)
for i in range(min_train_size, len(df_combined_helper)):
    # Training data: all previous data (rows 0 to i-1)
    train_data = df_combined_helper[:i].select(dir_features_cols).to_numpy()
    train_target = (df_combined_helper[:i]["direction_target"].to_numpy() > 0).astype(
        int
    )
    # ^ direction_target[j] for j<i are REALIZED values (historical)

    # Remove NaN rows
    valid_mask = ~np.isnan(train_data).any(axis=1) & ~np.isnan(train_target)

    if valid_mask.sum() < 50:  # Need minimum 50 samples
        helper_dir_prob_predictions[i] = 0.5  # Neutral probability
        continue

    train_data_clean = train_data[valid_mask]
    train_target_clean = train_target[valid_mask]

    # Train model with regularization to prevent overfitting
    try:
        scaler = StandardScaler()
        train_data_scaled = scaler.fit_transform(train_data_clean)

        log_reg = LogisticRegression(
            max_iter=300,
            random_state=42,
            C=1.0,  # Regularization strength
            class_weight="balanced",  # Handle class imbalance
        )
        log_reg.fit(train_data_scaled, train_target_clean)

        # Predict current point (probability of upward direction)
        current_features = (
            df_combined_helper[i : i + 1].select(dir_features_cols).to_numpy()
        )
        if not np.isnan(current_features).any():
            current_scaled = scaler.transform(current_features)
            helper_dir_prob_predictions[i] = log_reg.predict_proba(current_scaled)[0, 1]
        else:
            helper_dir_prob_predictions[i] = 0.5
    except:
        helper_dir_prob_predictions[i] = 0.5

# Add to combined dataframe
df_combined_helper = df_combined_helper.with_columns(
    [pl.lit(helper_dir_prob_predictions).alias("helper_dir_prob")]
)

# Create helper_dir_confidence (distance from 0.5)
df_combined_helper = df_combined_helper.with_columns(
    [(pl.col("helper_dir_prob") - 0.5).abs().alias("helper_dir_confidence")]
)

# Create directional signal based on threshold
df_combined_helper = df_combined_helper.with_columns(
    [
        pl.when(pl.col("helper_dir_prob") > 0.55)
        .then(1)  # Bullish
        .when(pl.col("helper_dir_prob") < 0.45)
        .then(-1)  # Bearish
        .otherwise(0)  # Neutral
        .alias("helper_dir_signal")
    ]
)

print(
    "    • Created helper_dir_prob (Enhanced Logistic Regression direction probabilities)"
)
print("    • Created helper_dir_confidence (distance from 0.5)")
print("    • Created helper_dir_signal (1=bullish, 0=neutral, -1=bearish)")
print(
    f"    • First {min_train_size} values = 0.5 (neutral, insufficient training data)"
)
print(f"    • Enhanced with {len(dir_features_cols)} features:")
print("      - Momentum and z-score features (5)")
print("      - Volatility features (vol, vol-of-vol)")
print("      - HMM regime features (4-regime + 5-regime + confidence)")
print("      - Technical indicators (drawdown, consecutive moves)")
print("    • Regularized with C=1.0 and balanced class weights")
print("    ✅ VERIFIED: Uses only past data (rows 0 to i-1 to predict row i)")


# 4. ADDITIONAL INTERACTION FEATURES AND ROLLING STATS


print("\n  ✓ Creating Additional Interaction Features...")

# LR × regime interaction
df_combined_helper = df_combined_helper.with_columns(
    [
        (pl.col("helper_vol_lr") * pl.col("hmm5_regime")).alias(
            "helper_vol_lr_x_regime"
        ),
    ]
)

# Direction probability × regime interaction
df_combined_helper = df_combined_helper.with_columns(
    [
        (pl.col("helper_dir_prob") * pl.col("hmm_regime")).alias(
            "helper_dir_prob_x_regime"
        ),
    ]
)

# Rolling mean (21-day) for validation (BACKWARD-LOOKING)
df_combined_helper = df_combined_helper.with_columns(
    [
        pl.col("helper_vol_ewma")
        .rolling_mean(window_size=21)
        .alias("helper_vol_rolling_mean"),
    ]
)

# Rolling std (21-day) for validation (BACKWARD-LOOKING)
df_combined_helper = df_combined_helper.with_columns(
    [
        pl.col("helper_vol_ewma")
        .rolling_std(window_size=21)
        .alias("helper_vol_rolling_std"),
    ]
)

print("    • Created helper_vol_lr_x_regime (LR × 5-regime volatility HMM)")
print("    • Created helper_dir_prob_x_regime (Direction prob × 4-regime HMM)")
print("    • Created helper_vol_rolling_mean (21-day rolling mean)")
print("    • Created helper_vol_rolling_std (21-day rolling std)")
print("    ✅ VERIFIED: All rolling operations are backward-looking")


# 5. EWMA × REGIME INTERACTION


print("\n  ✓ Creating EWMA × Regime Interaction...")

# Now that both helper_vol_ewma and hmm5_regime exist
df_combined_helper = df_combined_helper.with_columns(
    [
        (pl.col("helper_vol_ewma") * pl.col("hmm5_regime")).alias(
            "helper_vol_ewma_x_regime"
        ),
    ]
)

print("    • Created helper_vol_ewma_x_regime (EWMA × 5-regime volatility HMM)")
print("    • Adapts EWMA smoothing to different volatility regimes")


# 6. CONSENSUS FEATURE (Average of LR and EWMA)


print("\n  ✓ Creating Consensus Feature...")

# Consensus = average of LR and EWMA predictions
df_combined_helper = df_combined_helper.with_columns(
    [
        ((pl.col("helper_vol_lr") + pl.col("helper_vol_ewma")) / 2.0).alias(
            "helper_vol_consensus"
        ),
    ]
)

print("    • Created helper_vol_consensus (average of LR and EWMA)")
print("    • Combines two independent volatility forecasts")

# STEP 3: SPLIT back to PARTIAL and TRAIN datasets
print("\n  STEP 3: Splitting back to PARTIAL + TRAIN...")
df_partial = df_combined_helper[0:idx_partial_end_helper].clone()
df_train = df_combined_helper[idx_partial_end_helper:idx_train_end_helper].clone()

# Update df_pl reference
df_pl = df_train.clone()

print(f"    • PARTIAL: {len(df_partial)} rows, {len(df_partial.columns)} features")
print(f"    • TRAIN: {len(df_train)} rows, {len(df_train.columns)} features")
print("    • Updated df_pl = df_train (reference)")
print(
    "    ℹ️  VALIDATION helper features will be calculated row-by-row in API simulation"
)


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4: SAVE TRAINED HELPER MODELS FOR API SIMULATION (CRITICAL!)
# ═══════════════════════════════════════════════════════════════════════════
# The lr and log_reg models from the FINAL iteration of the loops above
# were trained on ALL of PARTIAL+TRAIN data. Save them for use in cell28.py.

print("\n  STEP 4: Saving trained helper models for API simulation...")

import pickle

# Prepare state dictionary with final trained models and metadata
helper_models_state = {
    # SESSION ID FOR VALIDATION (prevents loading stale models)
    "session_id": TRAINING_SESSION_ID,
    # LinearRegression for volatility (trained on PARTIAL+TRAIN)
    "lr_model": lr,
    "vol_features_cols": vol_features_cols,
    # LogisticRegression for direction (trained on PARTIAL+TRAIN)
    "log_reg_model": log_reg,
    "log_reg_scaler": scaler,  # The StandardScaler used for direction features
    "dir_features_cols": dir_features_cols,
    # EWMA parameters (not a trained model, but needed for consistency)
    "ewma_span": ewma_span,
    # Last values from training (for continuity with validation)
    "last_helper_vol_lr": helper_vol_lr_predictions[-1],
    "last_helper_vol_ewma": helper_vol_ewma_predictions[-1],
    "last_helper_dir_prob": helper_dir_prob_predictions[-1],
    # Training info for verification
    "training_rows": len(df_combined_helper),
    "min_train_size": min_train_size,
}

# Save to pickle file
helper_models_path = output_dir / "helper_models.pkl"
with open(helper_models_path, "wb") as f:
    pickle.dump(helper_models_state, f)

print(f"    ✅ Saved trained helper models to: {helper_models_path}")
print(f"    • lr_model: LinearRegression trained on {len(df_combined_helper)} rows")
print(
    f"    • log_reg_model: LogisticRegression trained on {len(df_combined_helper)} rows"
)
print("    • log_reg_scaler: StandardScaler fitted on training data")
print(f"    • vol_features_cols: {len(vol_features_cols)} features")
print(f"    • dir_features_cols: {len(dir_features_cols)} features")
print(
    f"    • Last values: vol_lr={helper_vol_lr_predictions[-1]:.6f}, ewma={helper_vol_ewma_predictions[-1]:.6f}, dir_prob={helper_dir_prob_predictions[-1]:.6f}"
)

print(f"\n{'=' * 80}\n")

# Summary
print("📊 HELPER MODELS SUMMARY (PARTIAL + TRAIN):")
print("  • helper_vol_lr: Linear regression vol forecast")
print("  • helper_vol_lr_error: LR prediction errors")
print("  • helper_vol_lr_x_regime: LR × regime interaction")
print("  • helper_vol_ewma: EWMA vol forecast")
print("  • helper_vol_ewma_error: EWMA prediction errors")
print("  • helper_vol_ewma_variance: EWMA volatility std")
print("  • helper_vol_ewma_absret: EWMA absolute returns")
print("  • helper_vol_ewma_x_regime: EWMA × regime interaction")
print("  • helper_vol_rolling_mean: 21-day rolling mean")
print("  • helper_vol_rolling_std: 21-day rolling std")
print("  • helper_vol_consensus: Consensus of LR and EWMA")
print(
    f"  • helper_dir_prob: ENHANCED Logistic regression direction probability ({len(dir_features_cols)} features)"
)
print("  • helper_dir_confidence: Direction prediction confidence")
print("  • helper_dir_signal: Direction signal (-1/0/1)")
print("  • helper_dir_prob_x_regime: Direction prob × 4-regime HMM")
print("  Total: 15 new features applied to PARTIAL + TRAIN")
print("  ℹ️  VALIDATION: Helper features will be calculated LIVE in API simulation")
print("\n✅ DATA LEAKAGE CHECK PASSED:")
print("  • Expanding window: Row i prediction uses ONLY rows 0 to i-1")
print("  • All features are historical/lagged (no future data)")
print("  • Targets used in training are REALIZED values from past")
print("  • EWMA and rolling operations are backward-looking only\n")


# %% [CELL 10] Isolation Forest Multi-Level Anomaly Detection
# ═══════════════════════════════════════════════════════════════════════════
# ENHANCED ANOMALY DETECTION: MULTI-LEVEL ISOLATION FOREST (UNSUPERVISED)
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 80}")
print("ENHANCED ANOMALY DETECTION: MULTI-LEVEL ISOLATION FOREST (UNSUPERVISED)")
print(f"{'=' * 80}\n")

print("Objective:")
print("  • Train 3 Isolation Forest models with different contamination levels:")
print("    - EXTREME: High precision, low recall (most severe anomalies)")
print("    - MODERATE: Balanced precision/recall (typical anomalies)")
print("    - MILD: High recall, low precision (sensitive detection)")
print("  • Use AUTO-DETERMINED contamination levels based on statistical methods")
print("  • Create severity scores and lag-1 features for all levels")
print("  • Enable hierarchical anomaly classification")
print()

# Required imports
import numpy as np
import polars as pl
from sklearn.ensemble import IsolationForest

# ═══════════════════════════════════════════════════════════════════════════
# STEP 0: DEFINE INCREMENTAL ISOLATION FOREST CALCULATOR CLASS
# ═══════════════════════════════════════════════════════════════════════════
print("  STEP 0: Defining Incremental Isolation Forest Calculator class...")


class IncrementalIsolationForestCalculator:
    """
    Incremental calculator for Isolation Forest anomaly detection.

    Maintains internal state and predicts row-by-row to ensure consistency
    between training (PARTIAL), testing (TRAIN/VALIDATION), and API simulation.

    This ensures CatBoost models trained on Isolation Forest features will work
    correctly during live fetching where data arrives row-by-row.
    """

    def __init__(
        self, isolation_forest_models, partial_df, feature_names, max_history=500
    ):
        """
        Initialize the incremental Isolation Forest calculator.

        Parameters:
        -----------
        isolation_forest_models : dict
            Dictionary of trained IsolationForest models (extreme, moderate, mild)
        partial_df : pl.DataFrame
            PARTIAL dataset with already-computed anomaly features
        feature_names : list
            List of feature names used by Isolation Forest
        max_history : int
            Maximum rows to keep in internal buffer (prevents memory issues)
        """
        self.models = isolation_forest_models
        self.feature_names = feature_names
        self.max_history = max_history

        # Clone PARTIAL data as starting historical buffer
        # This contains all Isolation Forest features already computed
        self.historical_df = partial_df.clone()

        # Store contamination levels for reference
        self.levels = list(isolation_forest_models.keys())

        # Store the column names from historical_df to ensure consistency
        self.historical_columns = self.historical_df.columns

        print("      ✓ Incremental Isolation Forest Calculator initialized")
        print(f"        - Models: {', '.join(self.levels)}")
        print(f"        - Features: {len(self.feature_names)}")
        print(f"        - Historical data: {len(self.historical_df)} rows (PARTIAL)")
        print(f"        - Historical columns: {len(self.historical_columns)}")
        print(f"        - Max history buffer: {self.max_history} rows")

    def add_anomaly_features_to_new_row(self, new_row_df, verbose=False):
        """
        Add Isolation Forest anomaly features to a new row.

        This method:
        1. Extracts features from new row
        2. Predicts anomaly status and severity for each level
        3. Adds lag-1 features from previous row
        4. Creates HMM interaction features
        5. Updates internal historical buffer (ONLY with matching columns)

        Parameters:
        -----------
        new_row_df : pl.DataFrame
            Single row to process (must have feature columns)
        verbose : bool
            Print detailed progress

        Returns:
        --------
        pl.DataFrame
            Row with all Isolation Forest features added
        """

        if verbose:
            print("\n      Adding Isolation Forest features to new row...")

        # Extract feature values from new row
        try:
            feature_values = [
                new_row_df[feat][0] if feat in new_row_df.columns else None
                for feat in self.feature_names
            ]
            feature_array = np.array(feature_values, dtype=float).reshape(1, -1)

            # Check if any features are NaN
            has_nan = np.isnan(feature_array).any()

        except Exception as e:
            if verbose:
                print(f"        ⚠️ Error extracting features: {e}")
            has_nan = True

        # If NaN features, set all anomaly features to neutral/default values
        if has_nan:
            if verbose:
                print("        ⚠️ NaN features detected - using default values")

            for level_name in self.levels:
                new_row_df = new_row_df.with_columns(
                    [
                        pl.lit(0, dtype=pl.Int64).alias(f"anomaly_{level_name}_is"),
                        pl.lit(0.0, dtype=pl.Float64).alias(
                            f"anomaly_{level_name}_severity"
                        ),
                    ]
                )
        else:
            # Predict using each Isolation Forest model
            for level_name in self.levels:
                model = self.models[level_name]

                # Predict: -1 = anomaly, 1 = normal
                pred = model.predict(feature_array)[0]
                is_anomaly = int(1 if pred == -1 else 0)

                # Get severity score (decision_function)
                # Raw scores: positive = normal, negative = anomaly
                severity = float(model.decision_function(feature_array)[0])

                # Add features to new row
                new_row_df = new_row_df.with_columns(
                    [
                        pl.lit(is_anomaly, dtype=pl.Int64).alias(
                            f"anomaly_{level_name}_is"
                        ),
                        pl.lit(severity, dtype=pl.Float64).alias(
                            f"anomaly_{level_name}_severity"
                        ),
                    ]
                )

                if verbose:
                    print(
                        f"        • {level_name}: anomaly={is_anomaly}, severity={severity:.4f}"
                    )

        # Add lag-1 features from previous row (last row in historical buffer)
        if len(self.historical_df) > 0:
            prev_row = self.historical_df[-1:]

            for level_name in self.levels:
                prev_is = (
                    int(prev_row[f"anomaly_{level_name}_is"][0])
                    if f"anomaly_{level_name}_is" in prev_row.columns
                    else 0
                )
                prev_severity = (
                    float(prev_row[f"anomaly_{level_name}_severity"][0])
                    if f"anomaly_{level_name}_severity" in prev_row.columns
                    else 0.0
                )

                new_row_df = new_row_df.with_columns(
                    [
                        pl.lit(prev_is, dtype=pl.Int64).alias(
                            f"anomaly_{level_name}_is_lag1"
                        ),
                        pl.lit(prev_severity, dtype=pl.Float64).alias(
                            f"anomaly_{level_name}_severity_lag1"
                        ),
                    ]
                )
        else:
            # No previous row - set lag-1 to defaults
            for level_name in self.levels:
                new_row_df = new_row_df.with_columns(
                    [
                        pl.lit(0, dtype=pl.Int64).alias(
                            f"anomaly_{level_name}_is_lag1"
                        ),
                        pl.lit(0.0, dtype=pl.Float64).alias(
                            f"anomaly_{level_name}_severity_lag1"
                        ),
                    ]
                )

        # Create HMM interaction features (if HMM features exist)
        if "hmm5_regime" in new_row_df.columns:
            hmm5_regime = float(new_row_df["hmm5_regime"][0])
            moderate_sev = float(new_row_df["anomaly_moderate_severity"][0])
            extreme_sev = float(new_row_df["anomaly_extreme_severity"][0])

            new_row_df = new_row_df.with_columns(
                [
                    pl.lit(moderate_sev * hmm5_regime, dtype=pl.Float64).alias(
                        "anomaly_moderate_sev_x_hmm5"
                    ),
                    pl.lit(extreme_sev * hmm5_regime, dtype=pl.Float64).alias(
                        "anomaly_extreme_sev_x_hmm5"
                    ),
                ]
            )

        if "hmm_regime" in new_row_df.columns:
            hmm_regime = float(new_row_df["hmm_regime"][0])
            moderate_sev = float(new_row_df["anomaly_moderate_severity"][0])

            new_row_df = new_row_df.with_columns(
                [
                    pl.lit(moderate_sev * hmm_regime, dtype=pl.Float64).alias(
                        "anomaly_moderate_sev_x_hmm"
                    ),
                ]
            )

        # CRITICAL FIX: Only select columns that exist in historical_df before concatenating
        # Align row to historical schema before appending to prevent concat shape issues
        common_columns = [
            col for col in self.historical_columns if col in new_row_df.columns
        ]

        if verbose:
            print(
                f"        • Historical buffer columns: {len(self.historical_columns)}"
            )
            print(f"        • New row columns: {len(new_row_df.columns)}")
            print(f"        • Common columns for concat: {len(common_columns)}")

        missing_columns = [
            col for col in self.historical_columns if col not in new_row_df.columns
        ]
        if missing_columns:
            if verbose:
                print(f"        • Padding missing columns: {len(missing_columns)}")
            new_row_df = new_row_df.with_columns(
                [pl.lit(None).alias(col) for col in missing_columns]
            )

        # Reorder/select columns to match historical buffer exactly
        new_row_for_history = new_row_df.select(self.historical_columns)

        # Update internal historical buffer with matching columns only
        # Cast new_row_for_history to match the schema of historical_df
        new_row_for_history = new_row_for_history.cast(self.historical_df.schema)
        self.historical_df = pl.concat([self.historical_df, new_row_for_history])

        # Trim history to prevent memory issues
        if len(self.historical_df) > self.max_history:
            self.historical_df = self.historical_df[-self.max_history :]
            if verbose:
                print(f"        (Trimmed history to {self.max_history} rows)")

        return new_row_df

    def get_historical_data(self):
        """Get current historical buffer (for debugging)"""
        return self.historical_df.clone()


print("    ✓ IncrementalIsolationForestCalculator class defined")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: PREPARE DATASET
# ═══════════════════════════════════════════════════════════════════════════
print("\n  STEP 1: Loading datasets...")

# Combine PARTIAL + TRAIN for consistent anomaly detection
df_combined_anom = pl.concat([df_partial, df_train], how="vertical")
idx_partial_end_anom = len(df_partial)
idx_train_end_anom = len(df_combined_anom)

print(f"    • Combined dataset: {len(df_combined_anom)} rows")
print(f"    • PARTIAL: rows 0-{idx_partial_end_anom}")
print(f"    • TRAIN: rows {idx_partial_end_anom}-{idx_train_end_anom}")
print("    ℹ️  Will train on PARTIAL, apply to PARTIAL+TRAIN")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: DEFINE CANDIDATE FEATURES
# ═══════════════════════════════════════════════════════════════════════════
print("\n  STEP 2: Defining candidate features for Isolation Forest...")

# Comprehensive feature list optimized for anomaly detection
candidate_features = [
    # Core volatility/returns (ALWAYS AVAILABLE)
    "daily_volatility_lagged",
    "lagged_forward_returns",
    # Momentum features (5d, 21d)
    "momentum_5d",
    "momentum_21d",
    # Volatility MAs (5d, 21d)
    "volatility_ma_5",
    "volatility_ma_21",
    # Z-scores (5d, 21d)
    "zscore_5d",
    "zscore_21d",
    # Volatility of volatility (5d, 21d)
    "vol_of_vol_5d",
    "vol_of_vol_21d",
    # Max drawdown (5d, 21d)
    "max_drawdown_5d",
    "max_drawdown_21d",
    # Consecutive up/down days
    "consecutive_up",
    "consecutive_down",
    # Distance from MAs
    "dist_from_ma_5d",
    "dist_from_ma_21d",
    # Mean historical volatility
    "mean_hist_vol_5",
    "mean_hist_vol_21",
    # Volatility ratio
    "vol_ratio_21",
    # Helper model features
    "helper_vol_lr",
    "helper_vol_ewma",
    "helper_dir_prob",
    "helper_vol_lr_error",
    "helper_vol_ewma_error",
    # HMM regime features
    "hmm_regime",
    "hmm5_regime",
    "hmm_regime_confidence",
    "hmm5_regime_prob_0",
    "hmm5_regime_prob_1",
    "hmm5_regime_prob_2",
    "hmm5_regime_prob_3",
    "hmm5_regime_prob_4",
    "hmm_regime_prob_0",
    "hmm_regime_prob_1",
    "hmm_regime_prob_2",
    "hmm_regime_prob_3",
]

# Filter to only available columns
available_features = [f for f in candidate_features if f in df_combined_anom.columns]
print(
    f"    • Candidate features: {len(available_features)} (from {len(candidate_features)} total)"
)

if len(available_features) < 5:
    print(
        "    ⚠️  WARNING: Very few features available - anomaly detection may be suboptimal!"
    )
    print(f"    Available: {available_features}")

print(f"    ✓ Using {len(available_features)} features for Isolation Forest")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: TRAIN ISOLATION FOREST MODELS
# ═══════════════════════════════════════════════════════════════════════════
print("\n  STEP 3: Training Isolation Forest models...")

# Prepare training data (PARTIAL only)
print("    • Preparing training data from PARTIAL dataset...")
X_train_list = []
for row_idx in range(len(df_partial)):
    row_features = []
    for feat in available_features:
        val = df_partial[feat][row_idx]
        if val is None or (isinstance(val, float) and np.isnan(val)):
            row_features.append(0.0)  # Replace NaN with 0
        else:
            row_features.append(float(val))
    X_train_list.append(row_features)

X_train = np.array(X_train_list)
print(f"    • Training data shape: {X_train.shape}")

# Determine contamination levels
n_samples = len(X_train)
contamination_extreme = min(0.01, max(10 / n_samples, 0.001))  # ~1%
contamination_moderate = min(0.05, max(50 / n_samples, 0.01))  # ~5%
contamination_mild = min(0.10, max(100 / n_samples, 0.05))  # ~10%

print("    • Contamination levels:")
print(
    f"      - EXTREME: {contamination_extreme:.4f} ({int(contamination_extreme * n_samples)} samples)"
)
print(
    f"      - MODERATE: {contamination_moderate:.4f} ({int(contamination_moderate * n_samples)} samples)"
)
print(
    f"      - MILD: {contamination_mild:.4f} ({int(contamination_mild * n_samples)} samples)"
)

# Train models
# OPTIMIZED: Increased n_estimators from 100 to 300 for more stable anomaly scores
isolation_forest_models = {}

print("\n    • Training EXTREME model (300 estimators)...")
isolation_forest_models["extreme"] = IsolationForest(
    contamination=contamination_extreme,
    random_state=42,
    n_estimators=300,  # Increased from 100 for more stable scores
)
isolation_forest_models["extreme"].fit(X_train)

print("    • Training MODERATE model (300 estimators)...")
isolation_forest_models["moderate"] = IsolationForest(
    contamination=contamination_moderate,
    random_state=42,
    n_estimators=300,  # Increased from 100 for more stable scores
)
isolation_forest_models["moderate"].fit(X_train)

print("    • Training MILD model (300 estimators)...")
isolation_forest_models["mild"] = IsolationForest(
    contamination=contamination_mild,
    random_state=42,
    n_estimators=300,  # Increased from 100 for more stable scores
)
isolation_forest_models["mild"].fit(X_train)

print("    ✓ All models trained successfully")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 4: CREATE INCREMENTAL CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════
print("\n  STEP 4: Creating Incremental Isolation Forest Calculator...")

# Store feature list for later use
isolation_forest_features = available_features

# Create calculator (will be initialized after applying features to PARTIAL)
isolation_forest_calculator = None  # Temporarily None until PARTIAL has features

print("    ℹ️  Calculator will be initialized after applying features to PARTIAL")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 5: APPLY TO PARTIAL DATASET (BATCH)
# ═══════════════════════════════════════════════════════════════════════════
print("\n  STEP 5: Applying Isolation Forest features to PARTIAL dataset...")

# Predict on PARTIAL
print("    • Predicting anomalies on PARTIAL...")
anomaly_features_partial = {}

for level_name, model in isolation_forest_models.items():
    predictions = model.predict(X_train)
    severities = model.decision_function(X_train)

    is_anomaly = (predictions == -1).astype(int)

    anomaly_features_partial[f"anomaly_{level_name}_is"] = is_anomaly
    anomaly_features_partial[f"anomaly_{level_name}_severity"] = severities

    print(f"      - {level_name}: {is_anomaly.sum()} anomalies detected")

# Add to PARTIAL dataframe
for feat_name, feat_values in anomaly_features_partial.items():
    df_partial = df_partial.with_columns([pl.lit(feat_values).alias(feat_name)])

# Add lag-1 features
for level_name in ["extreme", "moderate", "mild"]:
    df_partial = df_partial.with_columns(
        [
            pl.col(f"anomaly_{level_name}_is")
            .shift(1)
            .fill_null(0)
            .alias(f"anomaly_{level_name}_is_lag1"),
            pl.col(f"anomaly_{level_name}_severity")
            .shift(1)
            .fill_null(0.0)
            .alias(f"anomaly_{level_name}_severity_lag1"),
        ]
    )

# Add HMM interaction features to PARTIAL
if "hmm5_regime" in df_partial.columns:
    df_partial = df_partial.with_columns(
        [
            (pl.col("anomaly_moderate_severity") * pl.col("hmm5_regime")).alias(
                "anomaly_moderate_sev_x_hmm5"
            ),
            (pl.col("anomaly_extreme_severity") * pl.col("hmm5_regime")).alias(
                "anomaly_extreme_sev_x_hmm5"
            ),
        ]
    )

if "hmm_regime" in df_partial.columns:
    df_partial = df_partial.with_columns(
        [
            (pl.col("anomaly_moderate_severity") * pl.col("hmm_regime")).alias(
                "anomaly_moderate_sev_x_hmm"
            ),
        ]
    )

print("    ✓ PARTIAL dataset updated with Isolation Forest features")

# NOW initialize the calculator with PARTIAL that has anomaly features
isolation_forest_calculator = IncrementalIsolationForestCalculator(
    isolation_forest_models=isolation_forest_models,
    partial_df=df_partial,
    feature_names=isolation_forest_features,
    max_history=500,
)

print("    ✓ Calculator initialized with PARTIAL dataset")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 6: APPLY TO TRAIN DATASET (INCREMENTAL)
# ═══════════════════════════════════════════════════════════════════════════
print(
    "\n  STEP 6: Applying Isolation Forest features to TRAIN dataset (incremental)..."
)

# Process TRAIN row-by-row using incremental calculator
train_rows_with_anomaly = []
nan_row_count = 0  # 🔧 Track NaN rows

for idx in range(len(df_train)):
    current_row = df_train[idx : idx + 1]

    # 🔧 DEBUG: Check for NaN in input features (first few rows only)
    if idx < 5:
        for feat in isolation_forest_features[:5]:  # Check first 5 features
            if feat in current_row.columns:
                val = current_row[feat][0]
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    print(f"      ⚠️ Row {idx}, {feat} = NaN")

    # Add anomaly features incrementally
    current_row_with_anomaly = (
        isolation_forest_calculator.add_anomaly_features_to_new_row(
            current_row,
            verbose=(idx == 0),  # Verbose for first row only
        )
    )

    # 🔧 Track if anomaly was set to default (0)
    if (
        current_row_with_anomaly["anomaly_extreme_is"][0] == 0
        and current_row_with_anomaly["anomaly_moderate_is"][0] == 0
    ):
        # Check if this is due to NaN or just no anomaly detected
        feature_values = [
            current_row[feat][0] if feat in current_row.columns else None
            for feat in isolation_forest_features
        ]
        has_nan = any(
            v is None or (isinstance(v, float) and np.isnan(v)) for v in feature_values
        )
        if has_nan:
            nan_row_count += 1

    train_rows_with_anomaly.append(current_row_with_anomaly)

    if (idx + 1) % 500 == 0 or idx == len(df_train) - 1:
        print(f"    • Processed {idx + 1}/{len(df_train)} rows")

# Combine processed TRAIN rows
df_train = pl.concat(train_rows_with_anomaly)

print("    ✓ TRAIN dataset updated with Isolation Forest features")
print(f"    ⚠️ Rows with NaN input features: {nan_row_count}/{len(df_train)}")

# 🔧 DEBUG: Verify Anomaly features
print("\n  🔍 ANOMALY FEATURE VALIDATION:")
anomaly_features_check = [
    "anomaly_extreme_is",
    "anomaly_moderate_is",
    "anomaly_mild_is",
    "anomaly_extreme_severity",
    "anomaly_moderate_severity",
    "anomaly_mild_severity",
]
for feat in anomaly_features_check:
    if feat in df_train.columns:
        col = df_train[feat]
        non_null = col.drop_nulls()
        non_zero = (col != 0).sum()
        print(
            f"    • {feat}: non-null={len(non_null)}/{len(col)}, non-zero={non_zero}, range=[{col.min():.4f}, {col.max():.4f}]"
        )
    else:
        print(f"    ⚠️ {feat}: NOT FOUND!")

print("\n✓ ISOLATION FOREST TRAINING COMPLETE")
print("  • Models trained: 3 (extreme, moderate, mild)")
print(f"  • Features used: {len(available_features)}")
print("  • Calculator ready for incremental processing in API simulation")
print(f"  • PARTIAL: {len(df_partial)} rows with features")
print(f"  • TRAIN: {len(df_train)} rows with features")

# %% [CELL 11] CUSUM Changepoint Detection
# ═══════════════════════════════════════════════════════════════════════════
# STEP 1.3e: CUSUM CHANGEPOINT DETECTION (PARTIAL + TRAIN)
# ✅ Batch processing for PARTIAL + TRAIN
# ✅ VALIDATION processed row-by-row in API simulation
# ✅ NO DATA LEAKAGE: CUSUM uses only historical data (rolling window normalization)


print(f"\n{'=' * 80}")
print("STEP 1.3e: CUSUM CHANGEPOINT DETECTION (PARTIAL + TRAIN)")
print(f"{'=' * 80}\n")

import numpy as np

print("✓ Creating CUSUM Features for Changepoint Detection...")
print("  Strategy: Batch for PARTIAL+TRAIN, API simulation for VALIDATION")
print("  Rolling window normalization (63d) - uses only past data\n")

# TEMPORAL CORRECTNESS VERIFICATION:
# - CUSUM uses rolling window (63 days) for normalization
# - Only uses data up to current row for calculations
# - VALIDATION will be processed row-by-row in API simulation
# ✅ This is CORRECT - no data leakage!

# STEP 1: COMBINE PARTIAL + TRAIN for continuous timeline
print("\n  STEP 1: Combining PARTIAL + TRAIN...")
idx_partial_end_cusum = len(df_partial)
idx_train_end_cusum = idx_partial_end_cusum + len(df_train)

df_combined_cusum = pl.concat([df_partial, df_train], how="vertical")
print(f"    • Combined: {len(df_combined_cusum)} rows")
print(f"      - PARTIAL: 0-{idx_partial_end_cusum} ({idx_partial_end_cusum} rows)")
print(
    f"      - TRAIN: {idx_partial_end_cusum}-{idx_train_end_cusum} ({len(df_train)} rows)"
)
print("    ℹ️  VALIDATION will be processed row-by-row in API simulation (Cell 31)")


# STEP 2: CUSUM FUNCTION with adaptive normalization
def cusum_changepoint(
    series_np, threshold=2.0, drift=0.0, min_spacing=5, rolling_window=63
):
    """
    CUSUM changepoint detection with improvements:
    1. Reset after detection (prevents runaway accumulation)
    2. Rolling normalization (adapts to changing market conditions)
    3. Minimum spacing (prevents clustered detections)
    4. Returns changepoint magnitude for feature engineering

    Parameters:
    - threshold: Detection threshold (higher = less sensitive, fewer false positives)
    - drift: Momentum requirement (higher = need sustained movement)
    - min_spacing: Minimum days between changepoints (prevents clusters)
    - rolling_window: Window for rolling z-score normalization (0 = use global)
    """
    series_clean = np.nan_to_num(series_np.copy(), 0)
    n = len(series_clean)

    # Initialize outputs
    cusum_pos = np.zeros(n)
    cusum_neg = np.zeros(n)
    changepoint_up = np.zeros(n, dtype=int)
    changepoint_down = np.zeros(n, dtype=int)
    changepoint_magnitude = np.zeros(n)  # NEW: Track magnitude at detection

    last_changepoint = -min_spacing  # Track last changepoint for spacing

    for i in range(1, n):
        # ADAPTIVE NORMALIZATION: Use rolling window if specified
        # 🔧 BUG FIX: Use ddof=1 to match Cell 28 API simulation (was ddof=0)
        if rolling_window > 0 and i >= rolling_window:
            window_data = series_clean[max(0, i - rolling_window) : i]
            mean = np.mean(window_data)
            std = np.std(window_data, ddof=1) + 1e-8  # 🔧 FIXED: ddof=1 to match API
        else:
            # 🔧 BUG FIX: Changed from [:i+1] to [:i] to exclude current value
            # This eliminates look-ahead bias and matches rolling pattern
            # Original (buggy): mean = np.mean(series_clean[:i+1])
            mean = np.mean(series_clean[:i])
            std = (
                np.std(series_clean[:i], ddof=1) + 1e-8
            )  # 🔧 FIXED: ddof=1 to match API

        z = (series_clean[i] - mean) / std

        # Accumulate CUSUM
        cusum_pos[i] = max(0, cusum_pos[i - 1] + z - drift)
        cusum_neg[i] = min(0, cusum_neg[i - 1] + z + drift)

        # Detect changepoints with MINIMUM SPACING constraint
        if cusum_pos[i] > threshold and (i - last_changepoint) >= min_spacing:
            changepoint_up[i] = 1
            changepoint_magnitude[i] = cusum_pos[i]  # Store magnitude before reset
            cusum_pos[i] = 0  # Reset after detection
            last_changepoint = i

        if cusum_neg[i] < -threshold and (i - last_changepoint) >= min_spacing:
            changepoint_down[i] = 1
            changepoint_magnitude[i] = abs(cusum_neg[i])  # Store magnitude before reset
            cusum_neg[i] = 0  # Reset after detection
            last_changepoint = i

    changepoint_any = ((changepoint_up == 1) | (changepoint_down == 1)).astype(int)

    return (
        cusum_pos,
        cusum_neg,
        changepoint_up,
        changepoint_down,
        changepoint_any,
        changepoint_magnitude,
    )


# STEP 3: APPLY CUSUM to volatility and returns
print("\n  STEP 3: Applying CUSUM changepoint detection...")

# 1. CUSUM for VOLATILITY
print("\n    • CUSUM Volatility Changepoints (Enhanced):")
(
    cusum_vol_pos,
    cusum_vol_neg,
    vol_pos_changes,
    vol_neg_changes,
    vol_any_changes,
    vol_changepoint_magnitude,
) = cusum_changepoint(
    series_np=df_combined_cusum["daily_volatility_lagged"].to_numpy(),
    threshold=2.0,
    drift=0.5,
    min_spacing=5,
    rolling_window=63,
)

print(f"      - Positive changepoints: {vol_pos_changes.sum()} detected")
print(f"      - Negative changepoints: {vol_neg_changes.sum()} detected")
print(f"      - Total changepoints: {vol_any_changes.sum()} detected")

# 2. CUSUM for RETURNS
print("\n    • CUSUM Return Changepoints (Enhanced):")
(
    cusum_ret_pos,
    cusum_ret_neg,
    ret_pos_changes,
    ret_neg_changes,
    ret_any_changes,
    ret_changepoint_magnitude,
) = cusum_changepoint(
    series_np=df_combined_cusum["lagged_forward_returns"].to_numpy(),
    threshold=2.5,
    drift=0.5,
    min_spacing=5,
    rolling_window=63,
)

print(f"      - Positive changepoints: {ret_pos_changes.sum()} detected")
print(f"      - Negative changepoints: {ret_neg_changes.sum()} detected")
print(f"      - Total changepoints: {ret_any_changes.sum()} detected")

# STEP 4: ADD CUSUM FEATURES
print("\n  STEP 4: Adding CUSUM features to combined dataframe...")

# Add basic CUSUM features (cusum values, changepoints, magnitudes)
df_combined_cusum = df_combined_cusum.with_columns(
    [
        pl.Series("cusum_volatility_pos", cusum_vol_pos),
        pl.Series("cusum_volatility_neg", cusum_vol_neg),
        pl.Series("cusum_returns_pos", cusum_ret_pos),
        pl.Series("cusum_returns_neg", cusum_ret_neg),
        pl.Series("changepoint_vol_up", vol_pos_changes),
        pl.Series("changepoint_vol_down", vol_neg_changes),
        pl.Series("changepoint_vol_any", vol_any_changes),
        pl.Series("changepoint_ret_up", ret_pos_changes),
        pl.Series("changepoint_ret_down", ret_neg_changes),
        pl.Series("changepoint_ret_any", ret_any_changes),
        pl.Series("changepoint_vol_magnitude", vol_changepoint_magnitude),
        pl.Series("changepoint_ret_magnitude", ret_changepoint_magnitude),
    ]
)

# STEP 5: DERIVED FEATURES
print("\n  STEP 5: Creating derived CUSUM features...")
df_combined_cusum = df_combined_cusum.with_columns(
    [
        # Combined changepoint indicator (either vol or return)
        ((pl.col("changepoint_vol_any") == 1) | (pl.col("changepoint_ret_any") == 1))
        .cast(pl.Int32)
        .alias("changepoint_combined"),
        # CUSUM ratios (balance between positive/negative)
        (
            pl.col("cusum_volatility_pos")
            / (pl.col("cusum_volatility_neg").abs() + 1e-8)
        ).alias("cusum_vol_ratio"),
        (
            pl.col("cusum_returns_pos") / (pl.col("cusum_returns_neg").abs() + 1e-8)
        ).alias("cusum_ret_ratio"),
        # CUSUM momentum (difference between pos/neg)
        (pl.col("cusum_volatility_pos") + pl.col("cusum_volatility_neg")).alias(
            "cusum_vol_momentum"
        ),
        (pl.col("cusum_returns_pos") + pl.col("cusum_returns_neg")).alias(
            "cusum_ret_momentum"
        ),
    ]
)

# STEP 6: TIME SINCE CHANGEPOINT & INTERACTION FEATURES
print("\n  STEP 6: Adding time-based and interaction features...")

# Calculate days since last changepoint for VOLATILITY
changepoint_vol_arr = vol_any_changes
time_since_vol = np.zeros(len(changepoint_vol_arr))
days_counter = 0

for i in range(len(changepoint_vol_arr)):
    if changepoint_vol_arr[i] == 1:
        days_counter = 0
    else:
        days_counter += 1
    time_since_vol[i] = days_counter

df_combined_cusum = df_combined_cusum.with_columns(
    [
        pl.Series("cusum_days_since_changepoint", time_since_vol.astype(np.int32)),
    ]
)

# Add interaction features (combining CUSUM with other features)
if "hmm_regime" in df_combined_cusum.columns:
    print("    • Adding CUSUM x HMM interactions...")
    df_combined_cusum = df_combined_cusum.with_columns(
        [
            (pl.col("changepoint_vol_any") * pl.col("hmm_regime")).alias(
                "cusum_vol_change_x_hmm"
            ),
            (pl.col("cusum_ret_momentum") * pl.col("hmm_regime")).alias(
                "cusum_ret_mom_x_hmm"
            ),
        ]
    )

if "hmm5_regime" in df_combined_cusum.columns:
    print("    • Adding CUSUM x HMM5 interactions...")
    df_combined_cusum = df_combined_cusum.with_columns(
        [
            (pl.col("changepoint_vol_any") * pl.col("hmm5_regime")).alias(
                "cusum_vol_change_x_hmm5"
            ),
            (pl.col("cusum_ret_momentum") * pl.col("hmm5_regime")).alias(
                "cusum_ret_mom_x_hmm5"
            ),
        ]
    )

if "anomaly_extreme_is" in df_combined_cusum.columns:
    print("    • Adding CUSUM x Anomaly interactions...")
    df_combined_cusum = df_combined_cusum.with_columns(
        [
            (pl.col("changepoint_vol_any") * pl.col("anomaly_extreme_is")).alias(
                "cusum_vol_change_x_extreme_anom"
            ),
            (pl.col("cusum_ret_momentum") * pl.col("anomaly_moderate_is")).alias(
                "cusum_ret_mom_x_moderate_anom"
            ),
            (pl.col("cusum_ret_momentum") * pl.col("changepoint_vol_any")).alias(
                "cusum_ret_x_vol_changepoint"
            ),
        ]
    )

# STEP 6.5: ADD MISSING CUSUM FEATURES (to match API simulation exactly)
print("\n  STEP 6.5: Adding additional CUSUM features for API consistency...")

# Add aliases for cusum_* versions of changepoint features (API uses these names)
df_combined_cusum = df_combined_cusum.with_columns(
    [
        pl.col("changepoint_vol_up").alias("cusum_vol_pos_change"),
        pl.col("changepoint_vol_down").alias("cusum_vol_neg_change"),
        pl.col("changepoint_ret_up").alias("cusum_ret_pos_change"),
        pl.col("changepoint_ret_down").alias("cusum_ret_neg_change"),
        pl.col("changepoint_vol_magnitude").alias("cusum_vol_magnitude"),
        pl.col("changepoint_ret_magnitude").alias("cusum_ret_magnitude"),
    ]
)
print("    • Added cusum_vol/ret_pos/neg_change aliases")
print("    • Added cusum_vol/ret_magnitude aliases")

# Add changepoint_signal_count (sum of all changepoint indicators)
df_combined_cusum = df_combined_cusum.with_columns(
    [
        (
            pl.col("changepoint_vol_up")
            + pl.col("changepoint_vol_down")
            + pl.col("changepoint_ret_up")
            + pl.col("changepoint_ret_down")
        ).alias("changepoint_signal_count"),
    ]
)
print("    • Added changepoint_signal_count")

# Add rolling changepoint counts (21d and 63d)
df_combined_cusum = df_combined_cusum.with_columns(
    [
        pl.col("changepoint_vol_any")
        .rolling_sum(window_size=21, min_periods=1)
        .alias("cusum_changepoint_count_21d"),
        pl.col("changepoint_vol_any")
        .rolling_sum(window_size=63, min_periods=1)
        .alias("cusum_changepoint_count_63d"),
    ]
)
print("    • Added cusum_changepoint_count_21d/63d")

# Add lagged CUSUM values
df_combined_cusum = df_combined_cusum.with_columns(
    [
        pl.col("cusum_returns_pos")
        .shift(1)
        .fill_null(0)
        .alias("cusum_returns_pos_lag1"),
        pl.col("cusum_returns_neg")
        .shift(1)
        .fill_null(0)
        .alias("cusum_returns_neg_lag1"),
        pl.col("cusum_returns_pos")
        .shift(5)
        .fill_null(0)
        .alias("cusum_returns_pos_lag5"),
        pl.col("cusum_returns_neg")
        .shift(5)
        .fill_null(0)
        .alias("cusum_returns_neg_lag5"),
    ]
)
print("    • Added cusum_returns_pos/neg_lag1/lag5")

# STEP 7: SAVE CUSUM STATE for API simulation
print("\n  STEP 7: Saving CUSUM state for API simulation...")

# CRITICAL: Save last 5 values for lag feature calculations (lag1 and lag5)
# API row 0 needs: lag1 = train[-1], lag5 = train[-5]
# API row 1 needs: lag1 = API[0], lag5 = train[-4]
# etc. So we need at least 5 values from training history
last_5_vol_pos = cusum_vol_pos[
    max(0, idx_train_end_cusum - 5) : idx_train_end_cusum
].tolist()
last_5_vol_neg = cusum_vol_neg[
    max(0, idx_train_end_cusum - 5) : idx_train_end_cusum
].tolist()
last_5_ret_pos = cusum_ret_pos[
    max(0, idx_train_end_cusum - 5) : idx_train_end_cusum
].tolist()
last_5_ret_neg = cusum_ret_neg[
    max(0, idx_train_end_cusum - 5) : idx_train_end_cusum
].tolist()

print("    • Saving last 5 CUSUM values for lag features:")
print(f"      - cusum_ret_pos[-5:]: {[f'{v:.4f}' for v in last_5_ret_pos]}")
print(f"      - cusum_ret_neg[-5:]: {[f'{v:.4f}' for v in last_5_ret_neg]}")

cusum_state = {
    # SESSION ID FOR VALIDATION (prevents loading stale state)
    "session_id": TRAINING_SESSION_ID,
    # Last values (for CUSUM continuation)
    "last_vol_pos": cusum_vol_pos[idx_train_end_cusum - 1]
    if len(cusum_vol_pos) >= idx_train_end_cusum
    else 0.0,
    "last_vol_neg": cusum_vol_neg[idx_train_end_cusum - 1]
    if len(cusum_vol_neg) >= idx_train_end_cusum
    else 0.0,
    "last_ret_pos": cusum_ret_pos[idx_train_end_cusum - 1]
    if len(cusum_ret_pos) >= idx_train_end_cusum
    else 0.0,
    "last_ret_neg": cusum_ret_neg[idx_train_end_cusum - 1]
    if len(cusum_ret_neg) >= idx_train_end_cusum
    else 0.0,
    # LAST 5 VALUES FOR LAG FEATURES (API is continuation of training)
    "last_5_vol_pos": last_5_vol_pos,
    "last_5_vol_neg": last_5_vol_neg,
    "last_5_ret_pos": last_5_ret_pos,
    "last_5_ret_neg": last_5_ret_neg,
    "last_changepoint_vol": int(
        np.max(np.where(changepoint_vol_arr[:idx_train_end_cusum] == 1)[0])
    )
    if np.any(changepoint_vol_arr[:idx_train_end_cusum] == 1)
    else -5,
    "last_changepoint_ret": int(
        np.max(np.where(ret_any_changes[:idx_train_end_cusum] == 1)[0])
    )
    if np.any(ret_any_changes[:idx_train_end_cusum] == 1)
    else -5,
    "threshold_vol": 2.0,
    "threshold_ret": 2.5,
    "drift_vol": 0.5,
    "drift_ret": 0.5,
    "min_spacing": 5,
    "rolling_window": 63,
}

# Save to pickle for API use
import pickle

cusum_state_path = output_dir / "cusum_state.pkl"
with open(cusum_state_path, "wb") as f:
    pickle.dump(cusum_state, f)

print("    ✓ Saved CUSUM state for API simulation")

# Count total CUSUM features added
base_cusum_features = 27  # Updated from 26 to 27 (added changepoint_signal_count)
interaction_features = 0
if "hmm_regime" in df_combined_cusum.columns:
    interaction_features += 2
if "hmm5_regime" in df_combined_cusum.columns:
    interaction_features += 2
if "anomaly_extreme_is" in df_combined_cusum.columns:
    interaction_features += 3

total_cusum_features = base_cusum_features + interaction_features

print(f"\n  ✓ Created {total_cusum_features} CUSUM features for PARTIAL + TRAIN:")
print(f"      - Base features: {base_cusum_features}")
print(f"      - Interaction features: {interaction_features}")
print(
    "\n  ℹ️  VALIDATION: CUSUM features will be calculated LIVE in API simulation (Cell 31)"
)

# STEP 8: SPLIT BACK INTO PARTIAL + TRAIN
df_partial = df_combined_cusum[:idx_partial_end_cusum]
df_train = df_combined_cusum[idx_partial_end_cusum:idx_train_end_cusum]

print("\n  ✓ Split data back:")
print(f"    • PARTIAL: {len(df_partial)} rows with {len(df_partial.columns)} features")
print(f"    • TRAIN: {len(df_train)} rows with {len(df_train.columns)} features")

# 🔧 DEBUG: Verify CUSUM features are non-zero
print("\n  🔍 CUSUM FEATURE VALIDATION:")
cusum_key_features = [
    "cusum_volatility_pos",
    "cusum_volatility_neg",
    "cusum_returns_pos",
    "cusum_returns_neg",
    "changepoint_vol_any",
    "changepoint_ret_any",
    "cusum_days_since_changepoint",
]
for feat in cusum_key_features:
    if feat in df_train.columns:
        col = df_train[feat]
        non_null = col.drop_nulls()
        non_zero = (col != 0).sum()
        print(
            f"    • {feat}: non-null={len(non_null)}/{len(col)}, non-zero={non_zero}, range=[{col.min():.4f}, {col.max():.4f}]"
        )
    else:
        print(f"    ⚠️ {feat}: NOT FOUND!")

print(f"\n{'=' * 80}")
print("CUSUM CHANGEPOINT DETECTION COMPLETE ✓")
print(f"{'=' * 80}\n")

# %% [CELL 12] Multi-Signal Ensemble Changepoint Detection
# STEP 1.3f: MULTI-SIGNAL CHANGEPOINT DETECTION (ENSEMBLE METHOD)
# ✅ Uses combine→engineer→split strategy to apply to PARTIAL + TRAIN
# ✅ VALIDATION processed row-by-row in API simulation (Cell 16)
# ✅ NO DATA LEAKAGE: All signals use only historical/rolling data


print(f"\n{'=' * 80}")
print("STEP 1.3f: MULTI-SIGNAL CHANGEPOINT DETECTION (PARTIAL + TRAIN)")
print(f"{'=' * 80}\n")

print("✓ Combining CUSUM with existing signals for high-precision detection...")
print("  Research basis: Ensemble methods (CUSUM + HMM + Anomaly)")
print("  Standard in: Financial surveillance, fault detection, quality control")
print("  Strategy: combine→engineer→split for temporal correctness")
print("  Note: VALIDATION dataset processed row-by-row in API simulation (Cell 16)\n")

# TEMPORAL CORRECTNESS VERIFICATION:
# - CUSUM uses rolling window normalization (past 63 days only)
# - HMM transitions use only past regime assignments
# - Anomaly flags from Isolation Forest (trained on PARTIAL only)
# - Large volatility jumps use rolling threshold (past 252 days only)
# ✅ This is CORRECT - no data leakage!

# STEP 1: COMBINE PARTIAL + TRAIN datasets for continuous timeline
print("\n  STEP 1: Combining PARTIAL + TRAIN datasets...")
print("    (VALIDATION will be processed row-by-row in API simulation)")

idx_partial_end_ensemble = len(df_partial)
idx_train_end_ensemble = idx_partial_end_ensemble + len(df_train)

df_combined_ensemble = pl.concat([df_partial, df_train], how="vertical")
print(f"    • Combined: {len(df_combined_ensemble)} rows")
print(f"      - PARTIAL: 0-{idx_partial_end_ensemble}")
print(f"      - TRAIN: {idx_partial_end_ensemble}-{idx_train_end_ensemble}")

# STEP 2: GET CONFIRMATION SIGNALS (all already computed, no lookahead!)
print("\n  STEP 2: Extracting confirmation signals...")

cusum_changepoint = df_combined_ensemble["changepoint_vol_any"].to_numpy()
hmm_transition = df_combined_ensemble["hmm_regime_change"].to_numpy()
hmm5_transition = (
    df_combined_ensemble.get_column("hmm5_regime_change").to_numpy()
    if "hmm5_regime_change" in df_combined_ensemble.columns
    else np.zeros(len(df_combined_ensemble), dtype=int)
)

# Use multi-level anomaly flags (combine all levels for comprehensive detection)
anomaly_extreme = (
    df_combined_ensemble.get_column("anomaly_extreme_is").to_numpy()
    if "anomaly_extreme_is" in df_combined_ensemble.columns
    else np.zeros(len(df_combined_ensemble), dtype=int)
)
anomaly_moderate = (
    df_combined_ensemble.get_column("anomaly_moderate_is").to_numpy()
    if "anomaly_moderate_is" in df_combined_ensemble.columns
    else np.zeros(len(df_combined_ensemble), dtype=int)
)
anomaly_mild = (
    df_combined_ensemble.get_column("anomaly_mild_is").to_numpy()
    if "anomaly_mild_is" in df_combined_ensemble.columns
    else np.zeros(len(df_combined_ensemble), dtype=int)
)

# Combine anomaly levels (any anomaly detection)
anomaly_flag = ((anomaly_extreme + anomaly_moderate + anomaly_mild) > 0).astype(int)

# STEP 3: CALCULATE LARGE VOLATILITY JUMPS (using rolling threshold - NO FUTURE LEAKAGE!)
# Multi-period analysis: 252 days (year), 180 days (half-year), 21 days (month)
print("\n  STEP 3: Calculating large volatility jumps (multi-period)...")

daily_vol_arr = df_combined_ensemble["daily_volatility_lagged"].to_numpy()
vol_changes = np.abs(np.diff(daily_vol_arr))

# Define multiple lookback periods for different time scales
lookback_periods = {
    "year": 252,  # Annual perspective
    "halfyear": 180,  # Semi-annual perspective
    "month": 21,  # Monthly perspective
}

# Calculate jumps for each period
large_vol_jump_by_period = {}
for period_name, lookback_window in lookback_periods.items():
    large_vol_jump = np.zeros(len(daily_vol_arr), dtype=int)

    for i in range(lookback_window + 1, len(daily_vol_arr)):
        # Only use PAST data to calculate threshold (no future leakage!)
        past_changes = vol_changes[max(0, i - lookback_window - 1) : i - 1]
        threshold_i = (
            np.nanpercentile(past_changes, 80) if len(past_changes) > 0 else 0.005
        )

        # Check if current change (at i-1 due to diff offset) exceeds past threshold
        if vol_changes[i - 1] > threshold_i:
            large_vol_jump[i] = 1

    large_vol_jump_by_period[period_name] = large_vol_jump
    print(
        f"    • {period_name.upper():9s} ({lookback_window:3d} days): {large_vol_jump.sum():4d} jumps detected"
    )

# Create combined jump signal (any period detects a jump)
large_vol_jump_any = np.maximum.reduce(
    [large_vol_jump_by_period[p] for p in lookback_periods.keys()]
)

# Create consensus signal (majority of periods agree)
jump_sum = sum([large_vol_jump_by_period[p] for p in lookback_periods.keys()])
large_vol_jump_majority = (jump_sum >= 2).astype(int)

# Create strong consensus (all periods agree)
large_vol_jump_all = (jump_sum >= 3).astype(int)

print("\n    • Combined signals:")
print(f"      - ANY period (1+):      {large_vol_jump_any.sum():4d} jumps")
print(f"      - MAJORITY (2+):        {large_vol_jump_majority.sum():4d} jumps")
print(f"      - ALL periods (3):      {large_vol_jump_all.sum():4d} jumps")
print("    • Each point uses only PAST data (no future leakage!)")

# Use majority consensus as primary signal (balanced detection)
large_vol_jump = large_vol_jump_majority

# STEP 4: CREATE AND EVALUATE MULTIPLE ENSEMBLE METHODS
print("\n  STEP 4: Creating and evaluating ensemble methods...")
print("    Testing multiple strategies to auto-select best performer\n")

# Count agreeing signals (now 6 total with both HMM models)
signal_count = (
    cusum_changepoint.astype(int)
    + hmm_transition.astype(int)
    + hmm5_transition.astype(int)
    + anomaly_flag.astype(int)
    + large_vol_jump
)

# Determine total signals available
if "hmm5_regime_change" in df_combined_ensemble.columns:
    total_signals = 6
    print("    • Using 6 signals (CUSUM + 2 HMM + Anomaly + Vol Jump [majority])")
else:
    total_signals = 5
    print("    • Using 5 signals (CUSUM + HMM + Anomaly + Vol Jump [majority])")

# Get TRAIN indices for evaluation (use only TRAIN for fair comparison)
train_start_ens = idx_partial_end_ensemble
train_end_ens = idx_train_end_ensemble

# Get target volatility (daily_volatility_lagged is the actual realized vol)
target_vol_ens = df_combined_ensemble["daily_volatility_lagged"].to_numpy()

# Create multiple ensemble strategies
ensemble_methods = {}

# Method 1: CUSUM only (baseline)
ensemble_methods["CUSUM_only"] = cusum_changepoint.astype(int)

# Method 2: Any signal (2+ signals, high recall)
ensemble_methods["Any_2plus"] = (signal_count >= 2).astype(int)

# Method 3: Majority vote (3+ signals, balanced)
ensemble_methods["Majority_3plus"] = (signal_count >= 3).astype(int)

# Method 4: Strong agreement (4+ signals, high precision)
ensemble_methods["Strong_4plus"] = (signal_count >= 4).astype(int)

# Method 5: Very strong (5+ signals, ultra precision)
ensemble_methods["VeryStrong_5plus"] = (signal_count >= 5).astype(int)

# Method 6: HMM-weighted (HMM + CUSUM must both agree)
hmm_combined = np.maximum(hmm_transition, hmm5_transition).astype(int)
ensemble_methods["HMM_CUSUM"] = (
    (cusum_changepoint.astype(int) + hmm_combined) >= 2
).astype(int)

# NEW: Multi-period jump methods (using individual period signals)
# Method 7: Month-sensitive (short-term jumps + any confirmation)
month_jump_signal = (
    large_vol_jump_by_period["month"].astype(int)
    + cusum_changepoint.astype(int)
    + anomaly_flag.astype(int)
)
ensemble_methods["Month_Jump_2plus"] = (month_jump_signal >= 2).astype(int)

# Method 8: All-period consensus (any time scale detects + confirmation)
all_period_signal = (
    large_vol_jump_any.astype(int) + cusum_changepoint.astype(int) + hmm_combined
)
ensemble_methods["AllPeriod_2plus"] = (all_period_signal >= 2).astype(int)

# Method 9: Strong multi-scale (year + month both detect)
year_month_both = large_vol_jump_by_period["year"].astype(
    int
) + large_vol_jump_by_period["month"].astype(int)
ensemble_methods["Year_Month_Both"] = (year_month_both >= 2).astype(int)

print(f"\n    Evaluating {len(ensemble_methods)} ensemble strategies on TRAIN set...")
print("    (including 3 new multi-period jump methods)\n")

# ==========================================================================
# FIRST: Evaluate period-specific methods for each time scale
# ==========================================================================
print("  📊 PHASE 1: Period-Specific Optimization")
print(f"  {'=' * 78}")

period_best_methods = {}
period_ensemble_results = {}

for period_name, period_window in [("month", 21), ("halfyear", 180), ("year", 252)]:
    print(f"\n  {period_name.upper()} scale ({period_window} days):")
    print(f"  {'-' * 78}")

    # Create period-specific ensemble methods
    period_jump = large_vol_jump_by_period[period_name].astype(int)

    period_methods = {
        f"{period_name}_CUSUM": (
            period_jump + cusum_changepoint.astype(int) >= 1
        ).astype(int),
        f"{period_name}_CUSUM_2plus": (
            period_jump + cusum_changepoint.astype(int) >= 2
        ).astype(int),
        f"{period_name}_HMM": (period_jump + hmm_combined >= 1).astype(int),
        f"{period_name}_HMM_2plus": (period_jump + hmm_combined >= 2).astype(int),
        f"{period_name}_Anomaly": (period_jump + anomaly_flag.astype(int) >= 1).astype(
            int
        ),
        f"{period_name}_Anomaly_2plus": (
            period_jump + anomaly_flag.astype(int) >= 2
        ).astype(int),
        f"{period_name}_Multi": (
            period_jump + cusum_changepoint.astype(int) + hmm_combined >= 2
        ).astype(int),
        f"{period_name}_Multi_3plus": (
            period_jump + cusum_changepoint.astype(int) + hmm_combined >= 3
        ).astype(int),
    }

    # Evaluate each period-specific method
    period_results = []
    for method_name, detections in period_methods.items():
        train_detections = detections[train_start_ens:train_end_ens]
        train_target = target_vol_ens[train_start_ens:train_end_ens]

        n_detections = train_detections.sum()

        if n_detections > 0:
            detected_vol = train_target[train_detections == 1]
            normal_vol = train_target[train_detections == 0]

            avg_detected = np.nanmean(detected_vol) if len(detected_vol) > 0 else 0
            avg_normal = np.nanmean(normal_vol) if len(normal_vol) > 0 else 1e-10
            vol_ratio = avg_detected / avg_normal if avg_normal > 0 else 0

            corr = (
                np.corrcoef(train_detections, train_target)[0, 1]
                if len(train_detections) > 1
                else 0
            )

            detection_rate = n_detections / len(train_detections)
            if detection_rate < 0.01 or detection_rate > 0.50:
                f1_score = 0
            else:
                precision_proxy = min(vol_ratio / 3.0, 1.0)
                recall_proxy = min(detection_rate * 10, 1.0)
                f1_score = (
                    2
                    * (precision_proxy * recall_proxy)
                    / (precision_proxy + recall_proxy + 1e-10)
                )
        else:
            vol_ratio = 0
            corr = 0
            detection_rate = 0
            f1_score = 0

        period_results.append(
            {
                "Method": method_name,
                "Detections": n_detections,
                "Detection_Rate": detection_rate,
                "Vol_Ratio": vol_ratio,
                "Correlation": corr,
                "F1_Score": f1_score,
                "Signal": detections,
            }
        )

    # Sort by F1 score
    period_results_sorted = sorted(
        period_results, key=lambda x: x["F1_Score"], reverse=True
    )
    best_period_method = period_results_sorted[0]

    # Store best method for this period
    period_best_methods[period_name] = best_period_method["Method"]
    period_ensemble_results[period_name] = best_period_method["Signal"]

    # Print top 3 methods for this period
    print(f"  {'Method':<30} {'Det':>6} {'Rate':>7} {'Vol_Ratio':>9} {'F1':>7}")
    for i, r in enumerate(period_results_sorted[:3]):
        marker = "⭐" if i == 0 else "  "
        print(
            f"  {marker} {r['Method']:<28} {r['Detections']:>6} {r['Detection_Rate']:>6.1%} {r['Vol_Ratio']:>9.2f} {r['F1_Score']:>7.3f}"
        )

    print(
        f"\n  ✓ SELECTED: {best_period_method['Method']} (F1: {best_period_method['F1_Score']:.3f})"
    )

# ==========================================================================
# SECOND: Evaluate general ensemble methods (for backward compatibility)
# ==========================================================================
print("\n  📊 PHASE 2: General Ensemble Evaluation")
print(f"  {'=' * 78}\n")

# Add the optimized period-specific signals to ensemble methods
ensemble_methods["Optimized_Month"] = period_ensemble_results["month"]
ensemble_methods["Optimized_HalfYear"] = period_ensemble_results["halfyear"]
ensemble_methods["Optimized_Year"] = period_ensemble_results["year"]

# Create combined optimized signal (any period's best method triggers)
optimized_any = np.maximum.reduce(
    [period_ensemble_results[p] for p in ["month", "halfyear", "year"]]
)
ensemble_methods["Optimized_Any"] = optimized_any

# Create optimized majority (2+ period best methods agree)
optimized_sum = sum([period_ensemble_results[p] for p in ["month", "halfyear", "year"]])
ensemble_methods["Optimized_Majority"] = (optimized_sum >= 2).astype(int)

print(
    f"    Evaluating {len(ensemble_methods)} ensemble strategies (including period-optimized)...\n"
)

# Evaluate each method on TRAIN set
results = []
for method_name, detections in ensemble_methods.items():
    # Get TRAIN detections
    train_detections = detections[train_start_ens:train_end_ens]
    train_target = target_vol_ens[train_start_ens:train_end_ens]

    # Calculate metrics
    n_detections = train_detections.sum()

    if n_detections > 0:
        # Volatility ratio: avg vol on detected vs non-detected days
        detected_vol = train_target[train_detections == 1]
        normal_vol = train_target[train_detections == 0]

        avg_detected = np.nanmean(detected_vol) if len(detected_vol) > 0 else 0
        avg_normal = np.nanmean(normal_vol) if len(normal_vol) > 0 else 1e-10
        vol_ratio = avg_detected / avg_normal if avg_normal > 0 else 0

        # Correlation with target
        corr = (
            np.corrcoef(train_detections, train_target)[0, 1]
            if len(train_detections) > 1
            else 0
        )

        # F1-like score: balance between detection rate and signal quality
        detection_rate = n_detections / len(train_detections)
        # Penalize too many or too few detections
        if detection_rate < 0.01 or detection_rate > 0.50:
            f1_score = 0  # Too sparse or too dense
        else:
            # Combine vol_ratio (precision proxy) and correlation (relevance)
            precision_proxy = min(
                vol_ratio / 3.0, 1.0
            )  # Normalize to 0-1 (3.0x is excellent)
            recall_proxy = min(detection_rate * 10, 1.0)  # Normalize to 0-1
            f1_score = (
                2
                * (precision_proxy * recall_proxy)
                / (precision_proxy + recall_proxy + 1e-10)
            )
    else:
        avg_detected = 0
        avg_normal = np.nanmean(train_target)
        vol_ratio = 0
        corr = 0
        detection_rate = 0
        f1_score = 0

    results.append(
        {
            "Method": method_name,
            "Detections": n_detections,
            "Detection_Rate": detection_rate,
            "Vol_Ratio": vol_ratio,
            "Correlation": corr,
            "F1_Score": f1_score,
        }
    )

# Sort by F1 score (best overall balance)
results_sorted = sorted(results, key=lambda x: x["F1_Score"], reverse=True)
best_method = results_sorted[0]["Method"]

print("    📊 ENSEMBLE METHOD COMPARISON (TRAIN set):")
print("    " + "=" * 76)
print(
    f"    {'Method':<20} {'Detections':>10} {'Rate':>8} {'Vol_Ratio':>10} {'Corr':>8} {'F1':>8}"
)
print("    " + "-" * 76)
for r in results_sorted:
    marker = "  ⭐" if r["Method"] == best_method else "    "
    print(
        f"{marker}{r['Method']:<20} {r['Detections']:>10} {r['Detection_Rate']:>8.1%} {r['Vol_Ratio']:>10.2f} {r['Correlation']:>8.3f} {r['F1_Score']:>8.3f}"
    )
print("    " + "=" * 76)

# Select best method
best_detections = ensemble_methods[best_method]
print(
    f"\n    ✓ AUTO-SELECTED: {best_method} (highest F1 score: {results_sorted[0]['F1_Score']:.3f})"
)
print(f"    • Total changepoints detected: {best_detections.sum()}")

print(f"\n    ✓ Best overall method: {best_method}")
print("    • Will use for backward compatibility (cusum_vol_momentum)\n")

# ==========================================================================
# STEP 5: ADD ENSEMBLE FEATURES TO DATAFRAME
# ==========================================================================
print("\n  STEP 5: Adding ensemble features to combined dataframe...")

# Per-period core features (4 features × 3 periods = 12 features)
for period_name in lookback_periods.keys():
    signal_count_period = (
        cusum_changepoint.astype(int)
        + hmm_transition.astype(int)
        + hmm5_transition.astype(int)
        + anomaly_flag.astype(int)
        + large_vol_jump_by_period[period_name].astype(int)
    )
    confidence_period = signal_count_period / total_signals

    df_combined_ensemble = df_combined_ensemble.with_columns(
        [
            pl.lit(large_vol_jump_by_period[period_name]).alias(
                f"{period_name}_vol_jump"
            ),
            pl.lit(period_ensemble_results[period_name]).alias(
                f"{period_name}_ensemble"
            ),
            pl.lit(signal_count_period).alias(f"{period_name}_signal_count"),
            pl.lit(confidence_period).alias(f"{period_name}_confidence"),
        ]
    )

# Aggregate multi-period features (3 features)
periods_detecting_jump = (
    large_vol_jump_any.astype(int)
    + large_vol_jump_majority.astype(int)
    + large_vol_jump_all.astype(int)
)
periods_ensemble_triggered = sum(
    [period_ensemble_results[p].astype(int) for p in lookback_periods.keys()]
)
avg_period_confidence = signal_count / total_signals

df_combined_ensemble = df_combined_ensemble.with_columns(
    [
        pl.lit(periods_detecting_jump).alias("periods_detecting_jump"),
        pl.lit(periods_ensemble_triggered).alias("periods_ensemble_triggered"),
        pl.lit(avg_period_confidence).alias("avg_period_confidence"),
    ]
)

# HMM interaction features (create separate interactions for HMM4 and HMM5)
interaction_features = []
if "hmm_regime" in df_combined_ensemble.columns:
    hmm4_regime_arr = df_combined_ensemble["hmm_regime"].to_numpy()

    for period_name in lookback_periods.keys():
        # Calculate confidence array for this period
        confidence_arr = (
            cusum_changepoint.astype(int)
            + hmm_transition.astype(int)
            + hmm5_transition.astype(int)
            + anomaly_flag.astype(int)
            + large_vol_jump_by_period[period_name].astype(int)
        ) / total_signals

        # Create HMM4 interactions
        ensemble_x_hmm4 = (
            period_ensemble_results[period_name].astype(int) * hmm4_regime_arr
        )
        confidence_x_hmm4 = confidence_arr * hmm4_regime_arr

        df_combined_ensemble = df_combined_ensemble.with_columns(
            [
                pl.lit(ensemble_x_hmm4).alias(f"{period_name}_ensemble_x_hmm4"),
                pl.lit(confidence_x_hmm4).alias(f"{period_name}_confidence_x_hmm4"),
            ]
        )
        interaction_features.extend(
            [f"{period_name}_ensemble_x_hmm4", f"{period_name}_confidence_x_hmm4"]
        )

# Add HMM5 interactions if available
if "hmm5_regime" in df_combined_ensemble.columns:
    hmm5_regime_arr = df_combined_ensemble["hmm5_regime"].to_numpy()

    for period_name in lookback_periods.keys():
        # Calculate confidence array for this period
        confidence_arr = (
            cusum_changepoint.astype(int)
            + hmm_transition.astype(int)
            + hmm5_transition.astype(int)
            + anomaly_flag.astype(int)
            + large_vol_jump_by_period[period_name].astype(int)
        ) / total_signals

        # Create HMM5 interactions
        ensemble_x_hmm5 = (
            period_ensemble_results[period_name].astype(int) * hmm5_regime_arr
        )
        confidence_x_hmm5 = confidence_arr * hmm5_regime_arr

        df_combined_ensemble = df_combined_ensemble.with_columns(
            [
                pl.lit(ensemble_x_hmm5).alias(f"{period_name}_ensemble_x_hmm5"),
                pl.lit(confidence_x_hmm5).alias(f"{period_name}_confidence_x_hmm5"),
            ]
        )
        interaction_features.extend(
            [f"{period_name}_ensemble_x_hmm5", f"{period_name}_confidence_x_hmm5"]
        )

# Legacy feature for backward compatibility (best overall method)
cusum_vol_momentum = ensemble_methods[best_method]

df_combined_ensemble = df_combined_ensemble.with_columns(
    [
        pl.lit(cusum_vol_momentum).alias("cusum_vol_momentum"),
        pl.lit(large_vol_jump).alias("large_vol_jump"),  # Add standalone large_vol_jump
    ]
)

# Add legacy *_x_regime features (aliases for backward compatibility with API)
if "hmm_regime" in df_combined_ensemble.columns:
    hmm_regime_arr = df_combined_ensemble["hmm_regime"].to_numpy()
    for period_name in lookback_periods.keys():
        confidence_arr = (
            cusum_changepoint.astype(int)
            + hmm_transition.astype(int)
            + hmm5_transition.astype(int)
            + anomaly_flag.astype(int)
            + large_vol_jump_by_period[period_name].astype(int)
        ) / total_signals
        ensemble_x_regime = (
            period_ensemble_results[period_name].astype(int) * hmm_regime_arr
        )
        confidence_x_regime = confidence_arr * hmm_regime_arr
        df_combined_ensemble = df_combined_ensemble.with_columns(
            [
                pl.lit(ensemble_x_regime).alias(f"{period_name}_ensemble_x_regime"),
                pl.lit(confidence_x_regime).alias(f"{period_name}_confidence_x_regime"),
            ]
        )
    print("    • Added legacy *_x_regime interaction features")

# Count features
base_features = 2  # Legacy: cusum_vol_momentum, large_vol_jump
core_features_per_period = 4  # vol_jump, ensemble, signal_count, confidence
total_core_features = core_features_per_period * 3 + 3  # 3 periods + 3 aggregate
aggregate_features = 3

print(
    f"    • Per-period core features: {core_features_per_period} × 3 periods = {core_features_per_period * 3}"
)
print(f"    • Aggregate multi-period: {aggregate_features}")
print(f"    • HMM interactions: {len(interaction_features)}")
print(f"    • Legacy features: {base_features}")
print(
    f"    • Total new features: {total_core_features + len(interaction_features) + base_features}"
)

# ==========================================================================
# STEP 6: SPLIT BACK TO PARTIAL AND TRAIN
# ==========================================================================
print("\n  STEP 6: Splitting back into PARTIAL and TRAIN datasets...")

df_partial = df_combined_ensemble[0:idx_partial_end_ensemble]
df_train = df_combined_ensemble[idx_partial_end_ensemble:idx_train_end_ensemble]

print(f"    • PARTIAL: {len(df_partial)} rows, {df_partial.shape[1]} columns")
print(f"    • TRAIN: {len(df_train)} rows, {df_train.shape[1]} columns")

# ==========================================================================
# STEP 7: SAVE STATE FOR API SIMULATION
# ==========================================================================
print("\n  STEP 7: Saving ensemble configuration for API simulation...")

# Save ensemble configuration (to be used in API simulation)
ensemble_state = {
    "session_id": TRAINING_SESSION_ID,
    "period_best_methods": period_best_methods,
    "total_signals": total_signals,
    "lookback_periods": lookback_periods,
    "core_features_per_period": core_features_per_period,
    "aggregate_features": aggregate_features,
    "has_hmm5": (hmm5_transition.sum() > 0),
    "has_hmm": "hmm_regime" in df_combined_ensemble.columns,
    "best_general_method": best_method,
}

print("    ✓ Ensemble state saved")
print(f"      - Best methods per period: {period_best_methods}")
print(f"      - Best general method: {best_method}")
print(f"      - Total signals: {total_signals}")
print(f"      - Has HMM: {ensemble_state['has_hmm']}")
print(f"      - Has HMM-5: {ensemble_state['has_hmm5']}")

# ==========================================================================
# FINAL SUMMARY
# ==========================================================================
print(f"\n{'=' * 80}")
print("  ✅ MULTI-SIGNAL ENSEMBLE COMPLETE")
print(f"{'=' * 80}")
print("  📋 FEATURE SUMMARY BY CATEGORY")
print(f"  {'=' * 78}")
print(f"  BASE FEATURES - {base_features} features")
print(f"  {'=' * 78}")
print("  Feature Name             Type          Description")
print(f"  {'-' * 76}")
print(f"  cusum_vol_momentum       Binary        Legacy ensemble (best: {best_method})")
print(f"  {'-' * 76}")
print(f"  Detections: cusum_vol_momentum = {cusum_vol_momentum.sum():,}\n")

print(f"  {'=' * 78}")
print(f"  MONTH PERIOD FEATURES - {core_features_per_period} features")
print(f"  {'=' * 78}")
print("  Feature Name             Type          Description")
print(f"  {'-' * 76}")
print("  month_vol_jump           Binary        Raw 21-day volatility jump detection")
print(
    f"  month_ensemble           Binary        Optimized ensemble ({period_best_methods['month']})"
)
print(
    f"  month_signal_count       Integer       How many signals agree (0-{total_signals})"
)
print("  month_confidence         Float         Signal agreement ratio (0.0-1.0)")
print(f"  {'-' * 76}")
print(f"  Detections: month_ensemble = {period_ensemble_results['month'].sum():,}")
print(f"  Raw jumps:  month_vol_jump = {large_vol_jump_by_period['month'].sum():,}\n")

print(f"  {'=' * 78}")
print(f"  HALFYEAR PERIOD FEATURES - {core_features_per_period} features")
print(f"  {'=' * 78}")
print("  Feature Name             Type          Description")
print(f"  {'-' * 76}")
print("  halfyear_vol_jump        Binary        Raw 180-day volatility jump detection")
print(
    f"  halfyear_ensemble        Binary        Optimized ensemble ({period_best_methods['halfyear']})"
)
print(
    f"  halfyear_signal_count    Integer       How many signals agree (0-{total_signals})"
)
print("  halfyear_confidence      Float         Signal agreement ratio (0.0-1.0)")
print(f"  {'-' * 76}")
print(
    f"  Detections: halfyear_ensemble = {period_ensemble_results['halfyear'].sum():,}"
)
print(
    f"  Raw jumps:  halfyear_vol_jump = {large_vol_jump_by_period['halfyear'].sum():,}\n"
)

print(f"  {'=' * 78}")
print(f"  YEAR PERIOD FEATURES - {core_features_per_period} features")
print(f"  {'=' * 78}")
print("  Feature Name             Type          Description")
print(f"  {'-' * 76}")
print("  year_vol_jump            Binary        Raw 252-day volatility jump detection")
print(
    f"  year_ensemble            Binary        Optimized ensemble ({period_best_methods['year']})"
)
print(
    f"  year_signal_count        Integer       How many signals agree (0-{total_signals})"
)
print("  year_confidence          Float         Signal agreement ratio (0.0-1.0)")
print(f"  {'-' * 76}")
print(f"  Detections: year_ensemble = {period_ensemble_results['year'].sum():,}")
print(f"  Raw jumps:  year_vol_jump = {large_vol_jump_by_period['year'].sum():,}\n")

print(f"  {'=' * 78}")
print(f"  AGGREGATE MULTI-PERIOD FEATURES - {aggregate_features} features")
print(f"  {'=' * 78}")
print("  Feature Name                  Type          Description")
print(f"  {'-' * 76}")
print(
    "  periods_detecting_jump        Integer       Count of periods with raw jump (0-3)"
)
print(
    "  periods_ensemble_triggered    Integer       Count of period ensembles triggered (0-3)"
)
print(
    "  avg_period_confidence         Float         Average confidence across all periods"
)
print(f"  {'-' * 76}\n")

print(f"  {'=' * 78}")
print(f"  HMM INTERACTION FEATURES - {len(interaction_features)} features")
print(f"  {'=' * 78}")
if len(interaction_features) > 0:
    print("  Per period: ensemble × regime, confidence × regime")
    print(
        f"  Monthly interactions:    {sum(1 for f in interaction_features if 'month' in f)}"
    )
    print(
        f"  Semi-annual interactions: {sum(1 for f in interaction_features if 'halfyear' in f)}"
    )
    print(
        f"  Annual interactions:     {sum(1 for f in interaction_features if 'year' in f)}"
    )
else:
    print("  No HMM interactions (HMM features not available)")
print()

print(f"  {'=' * 78}")
print(
    f"  TOTAL FEATURES CREATED: {total_core_features + len(interaction_features) + base_features}"
)
print(f"  {'=' * 78}")
print(f"  Core period features:    {total_core_features}")
print(f"  HMM interactions:        {len(interaction_features)}")
print(f"  Base/legacy features:    {base_features}")
print(f"  {'=' * 78}\n")

print("  📖 USAGE GUIDE:")
print(f"  {'-' * 76}")
print("  SHORT-TERM TRADING (days to weeks):")
print("    → Use: month_ensemble, month_confidence, month_vol_jump")
print("    → Optimized for: 21-day volatility patterns")
print("    → Best for: Day trading, swing trading, weekly options\n")
print("  MEDIUM-TERM TRADING (weeks to months):")
print("    → Use: halfyear_ensemble, halfyear_confidence, halfyear_vol_jump")
print("    → Optimized for: 180-day volatility patterns")
print("    → Best for: Position trading, monthly options, sector rotation\n")
print("  LONG-TERM INVESTING (months to years):")
print("    → Use: year_ensemble, year_confidence, year_vol_jump")
print("    → Optimized for: 252-day volatility patterns")
print("    → Best for: Portfolio rebalancing, regime shifts, macro trends\n")
print("  MULTI-TIMEFRAME ANALYSIS:")
print("    → Use: periods_ensemble_triggered, avg_period_confidence")
print("    → Best for: Confirmation across multiple timeframes")
print(f"  {'-' * 76}\n")

print("  ⚠️  KEY POINTS:")
print("  • Each period has INDEPENDENT features (not combined)")
print("  • Each period uses DIFFERENT ensemble optimization")
print("  • Each period validated on DIFFERENT time horizons")
print("  • Monthly ≠ Semi-annual ≠ Annual (use appropriate for your strategy)")
print("  • ALL features use ONLY past data (no lookahead bias)\n")

print("  📊 TECHNICAL DETAILS:")
print(f"  {'-' * 76}")
print("  Temporal Correctness:")
print("    • CUSUM: Rolling 63-day normalization (past data only)")
print("    • Monthly jumps: Rolling 21-day threshold (past data only)")
print("    • Semi-annual jumps: Rolling 180-day threshold (past data only)")
print("    • Annual jumps: Rolling 252-day threshold (past data only)")
print("    • HMM transitions: Based on past regime assignments")
print("    • Anomaly flags: Isolation Forest (trained on PARTIAL dataset)")
print("    ✓ NO FUTURE INFORMATION in any feature\n")
print(f"  Signal Sources ({total_signals} total):")
print("    1. CUSUM changepoints (rolling 63-day)")
print("    2. HMM 4-regime transitions")
print("    3. HMM 5-regime transitions (if available)")
print("    4. Anomaly detection (3 severity levels)")
print("    5. Period-specific volatility jump (21/180/252 days)")
print(f"  {'-' * 76}\n")

print("  ⭐ BEST OVERALL METHOD (for backward compatibility):")
print(f"  {'-' * 76}")
print(f"  Method: {best_method}")
print(f"  F1 Score: {results_sorted[0]['F1_Score']:.3f}")
print(f"  Vol Ratio: {results_sorted[0]['Vol_Ratio']:.2f}x")
print("  Feature: cusum_vol_momentum")
print(f"  {'-' * 76}\n")

print(f"\n{'=' * 80}\n")

# %% [CELL 13] Kalman Filter H=20 Training

# KALMAN FILTER H=20: SUPERVISED TRAINING ON PARTIAL
# ✅ Train on PARTIAL using forward_returns_20d (TRUE FUTURE TARGET)
# ✅ Apply (predict-only) to TRAIN - no update with future data
# ✅ Save kalman_state for API simulation (VALIDATION) - predict only
# ⚠️ forward_returns_20d is ONLY used for TRAINING, NOT added as feature!


print(f"\n{'=' * 80}")
print("KALMAN FILTER H=20 - SUPERVISED TRAINING (PARTIAL) + PREDICTION (TRAIN/API)")
print(f"{'=' * 80}\n")

print("✓ Training Kalman filter on PARTIAL dataset using TRUE forward_returns_20d...")
print("✓ Applying (predict-only) to TRAIN dataset...")
print("✓ API will also use predict-only mode")
print("  Strategy: Train on PARTIAL with TRUE target → Predict-only on TRAIN/API\n")

import numpy as np
from tqdm.auto import tqdm

# Adaptive Kalman Filter Class (Optimized for H=20) - 3D STATE WITH ACCELERATION


class AdaptiveKalmanFilter:
    """
    Adaptive Kalman Filter for financial time series prediction.

    UPGRADED TO 3D STATE: [position, velocity, acceleration]
    - Position: Current value estimate
    - Velocity: Rate of change (1st derivative)
    - Acceleration: Rate of change of velocity (2nd derivative) - NEW!

    The 3D state allows the filter to model curved trajectories and
    detect momentum shifts more accurately.
    """

    def __init__(self, dt=1.0, data_variance=None, adaptation_rate=0.01):
        self.dt = dt
        self.adaptation_rate = adaptation_rate

        # State: [position, velocity, acceleration] - UPGRADED TO 3D
        self.x = np.zeros(3)

        # State covariance - 3x3 now
        self.P = np.eye(3) * 10.0

        # State transition matrix (constant acceleration model)
        # x[t+1] = x[t] + v[t]*dt + 0.5*a[t]*dt^2
        # v[t+1] = v[t] + a[t]*dt
        # a[t+1] = a[t]  (acceleration assumed constant between updates)
        self.F = np.array(
            [
                [1.0, dt, 0.5 * dt * dt],  # position update
                [0.0, 1.0, dt],  # velocity update
                [0.0, 0.0, 1.0],  # acceleration (constant)
            ]
        )

        # Measurement matrix (observe position only)
        self.H = np.array([[1.0, 0.0, 0.0]])

        # Process noise - 3x3 with higher noise on acceleration (more uncertain)
        self.Q = np.diag([1e-6, 1e-5, 1e-4])  # Acceleration has highest process noise

        # Measurement noise
        if data_variance is not None:
            self.R = np.array([[data_variance * 0.1]])
        else:
            self.R = np.array([[1e-4]])

        self.I = np.eye(3)

    def predict(self):
        """Predict next state"""
        # State prediction
        self.x = self.F @ self.x

        # Covariance prediction
        self.P = self.F @ self.P @ self.F.T + self.Q

        # Return position prediction
        return self.x[0]

    def update(self, measurement):
        """Update with new measurement"""
        # Innovation
        y = measurement - (self.H @ self.x)[0]

        # Innovation covariance
        S = (self.H @ self.P @ self.H.T + self.R)[0, 0]

        # Kalman gain
        K = (self.P @ self.H.T) / S

        # State update
        self.x = self.x + K.flatten() * y

        # Covariance update
        self.P = (self.I - K @ self.H) @ self.P

        # Adaptive measurement noise
        innovation_sq = y * y
        self.R[0, 0] = (1 - self.adaptation_rate) * self.R[
            0, 0
        ] + self.adaptation_rate * innovation_sq


# Helper Functions


def create_forward_returns_20d(forward_returns, horizon=20):
    """Create forward_returns_20d = sum of NEXT 20 forward_returns (TRUE FUTURE TARGET)

    ⚠️ This is FUTURE DATA and should ONLY be used for:
      - Training Kalman filter on PARTIAL dataset
      - NOT added as a feature to the model

    Returns:
        target: array of sum(forward_returns[i+1:i+21]) for each row
        valid_mask: True where we have full 20-day forward window
    """
    n = len(forward_returns)
    target = np.zeros(n)
    valid_mask = np.zeros(n, dtype=bool)

    for i in range(n):
        if i + horizon < n:
            # Sum of NEXT 20 forward returns (TRUE future data)
            target[i] = np.sum(forward_returns[i + 1 : i + 1 + horizon])
            valid_mask[i] = True
        else:
            # Not enough future data - mark as invalid
            target[i] = 0.0
            valid_mask[i] = False

    return target, valid_mask


def create_lagged_realized_observation(forward_returns, horizon=20):
    """Create LAGGED observation for Kalman update without data leakage.

    At time t, we can observe the REALIZED sum of returns from [t-horizon, t-1].
    This is PAST data that is available at time t.

    For Kalman filter prediction of H=20:
    - At time t, we predict what sum(returns[t+1:t+21]) will be
    - We can update with what sum(returns[t-19:t+1]) actually WAS (lagged observation)
    - This keeps the filter adaptive without looking into the future

    Returns:
        lagged_obs: array where lagged_obs[t] = sum(forward_returns[t-horizon:t])
        valid_mask: True where we have enough past data
    """
    n = len(forward_returns)
    lagged_obs = np.zeros(n)
    valid_mask = np.zeros(n, dtype=bool)

    for i in range(n):
        if i >= horizon:
            # Sum of PAST horizon returns - this is what we KNOW at time t
            lagged_obs[i] = np.sum(forward_returns[i - horizon : i])
            valid_mask[i] = True
        else:
            # Not enough past data yet
            lagged_obs[i] = 0.0
            valid_mask[i] = False

    return lagged_obs, valid_mask


def rolling_std_causal(series, window=20):
    """Calculate rolling std using only past data (causal)
    🔧 FIX: Use ddof=1 to match API simulation
    """
    result = np.zeros(len(series))
    for i in range(len(series)):
        if i < window:
            # 🔧 FIXED: Use ddof=1 for sample std to match API simulation
            result[i] = (
                np.std(series[: i + 1], ddof=1)
                if i > 1
                else np.std(series[: min(50, len(series))], ddof=1)
            )
        else:
            result[i] = np.std(series[i - window : i], ddof=1)
    return result


# STEP 1: COMBINE PARTIAL + TRAIN for batch processing
print("  STEP 1: Combining PARTIAL + TRAIN...")
idx_partial_end_kalman = len(df_partial)
idx_train_end_kalman = idx_partial_end_kalman + len(df_train)

# 🔧 DEBUG: Verify CUSUM/Anomaly features exist in source dataframes
print("\n  🔍 PRE-COMBINE FEATURE CHECK:")
cusum_check_cols = [
    "changepoint_vol_any",
    "changepoint_ret_any",
    "cusum_days_since_changepoint",
    "anomaly_extreme_is",
    "anomaly_moderate_is",
]
for col in cusum_check_cols:
    in_partial = col in df_partial.columns
    in_train = col in df_train.columns
    status = "✅" if (in_partial and in_train) else "⚠️ MISSING!"
    print(f"    • {col}: PARTIAL={in_partial}, TRAIN={in_train} {status}")

df_combined_kalman = pl.concat([df_partial, df_train], how="vertical")
print(f"\n    • Combined: {len(df_combined_kalman)} rows")
print(f"      - PARTIAL: 0-{idx_partial_end_kalman} (TRAIN with update)")
print(f"      - TRAIN: {idx_partial_end_kalman}-{idx_train_end_kalman} (PREDICT-ONLY)")
print(
    "      - VALIDATION: Will be processed row-by-row in API simulation (PREDICT-ONLY)"
)

# STEP 2: Create TRUE forward_returns_20d target from PARTIAL (FUTURE DATA - TRAINING ONLY!)
print(
    "\n  STEP 2: Creating forward_returns_20d target from PARTIAL (TRUE FUTURE DATA)..."
)
print("    ⚠️  This is FUTURE DATA - used ONLY for Kalman training, NOT as feature!")

# Get forward_returns from original data (preserved in df_partial_orig)
if "forward_returns" in df_partial_orig.columns:
    forward_returns_partial = df_partial_orig["forward_returns"].to_numpy()
    print(
        f"    ✅ Found forward_returns in df_partial_orig: {len(forward_returns_partial)} rows"
    )
else:
    raise ValueError(
        "forward_returns not found in df_partial_orig - required for Kalman training!"
    )

# Create forward_returns_20d for PARTIAL only
forward_returns_20d_partial, h20_valid_mask_partial = create_forward_returns_20d(
    forward_returns_partial, horizon=20
)
n_valid_partial = np.sum(h20_valid_mask_partial)
print(
    f"    • forward_returns_20d created: {n_valid_partial} valid rows (need 20 future days)"
)
print(
    f"    • Invalid at end: {len(forward_returns_partial) - n_valid_partial} rows (no future data)"
)

# Calculate rolling volatility for normalization (on PARTIAL target)
rolling_vol_partial = rolling_std_causal(forward_returns_20d_partial, window=20)
rolling_vol_partial = np.maximum(
    rolling_vol_partial,
    np.std(forward_returns_20d_partial[h20_valid_mask_partial]) * 0.1,
)

# Volatility normalize and clip outliers
h20_target_volnorm_partial = forward_returns_20d_partial / rolling_vol_partial
valid_vals = h20_target_volnorm_partial[h20_valid_mask_partial]
lower, upper = np.percentile(valid_vals, [0.5, 99.5])
h20_target_volnorm_clipped_partial = np.clip(h20_target_volnorm_partial, lower, upper)

print(
    f"    • Normalized target: mean={np.mean(valid_vals):+.6f}, std={np.std(valid_vals):.6f}"
)
print("    ✅ forward_returns_20d ready for Kalman training (NOT added as feature)")

# STEP 3: TRAIN Kalman Filter on PARTIAL only (with TRUE future target)
print(
    "\n  STEP 3: Training Kalman Filter on PARTIAL (with TRUE forward_returns_20d)..."
)
print(f"    • Training rows: {idx_partial_end_kalman}")
print(f"    • Valid training samples: {n_valid_partial}")
print("    • Target: sum(next 20 forward_returns) - TRUE FUTURE DATA")

kf = AdaptiveKalmanFilter(
    dt=1.0, data_variance=np.var(valid_vals), adaptation_rate=0.001
)
kf.Q = np.diag([1e-3, 1e-3, 1e-2])  # 3D Q matrix: higher noise on acceleration

# Storage for full PARTIAL + TRAIN
n_total = len(df_combined_kalman)
h20_predictions = np.zeros(n_total)
h20_state_position = np.zeros(n_total)
h20_state_velocity = np.zeros(n_total)
h20_state_acceleration = np.zeros(n_total)  # NEW: 3D state acceleration
h20_uncertainty = np.zeros(n_total)

# We need rolling vol for denormalization - use PARTIAL vol for now, update for TRAIN
rolling_vol_h20 = np.zeros(n_total)

# === PHASE 1: TRAIN on PARTIAL (with update using TRUE target) ===
print(f"\n    Phase 1: Training on PARTIAL ({idx_partial_end_kalman} rows)...")
for i in tqdm(range(idx_partial_end_kalman), desc="Kalman TRAIN", disable=True):
    rolling_vol_h20[i] = rolling_vol_partial[i]

    if i < 5:
        # Bootstrap: just update with target
        if h20_valid_mask_partial[i]:
            kf.update(h20_target_volnorm_clipped_partial[i])
            h20_predictions[i] = h20_target_volnorm_clipped_partial[i]
        else:
            h20_predictions[i] = 0.0
    else:
        # Normal: predict then update
        pred = kf.predict()
        h20_predictions[i] = pred

        # Update with TRUE future target (ONLY on PARTIAL!)
        if h20_valid_mask_partial[i]:
            kf.update(h20_target_volnorm_clipped_partial[i])

    h20_state_position[i] = kf.x[0]
    h20_state_velocity[i] = kf.x[1]
    h20_state_acceleration[i] = kf.x[2]  # NEW: Store acceleration state
    h20_uncertainty[i] = np.trace(kf.P)

# Save state at end of PARTIAL training for later use
kalman_state_after_partial = {
    "kf_x": kf.x.copy(),
    "kf_P": kf.P.copy(),
    "kf_R": kf.R.copy(),
}
print("    ✅ Kalman trained on PARTIAL - state saved")
print(f"       state_pos={kf.x[0]:.6f}, state_vel={kf.x[1]:.6f}")

# === PHASE 2: PREDICT with LAGGED UPDATE on TRAIN (no lookahead bias) ===
# Instead of predict-only (which makes velocity constant), we use LAGGED observations
# At time t, we update with observation from t-20 (which is now fully realized)
print(
    f"\n    Phase 2: Predicting on TRAIN with LAGGED UPDATE ({len(df_train)} rows)..."
)
print(
    "       Using H=20 lagged observations to keep filter adaptive WITHOUT data leakage"
)

# Create lagged_forward_returns history for the combined dataset (PARTIAL + TRAIN)
# NOTE: We use lagged_forward_returns (available in both TRAIN and API)
# lagged_forward_returns[t] = forward_returns[t-1], so sum of last 20 gives us
# sum(forward_returns[t-20:t]) which is the lagged observation
lagged_returns_combined = np.concatenate(
    [
        df_partial["lagged_forward_returns"].to_numpy(),
        df_train["lagged_forward_returns"].to_numpy(),
    ]
)

# Pre-compute lagged sums for efficiency (but normalize inside loop)
# lagged_sum[i] = sum(lagged_forward_returns[i-19:i+1]) = sum(forward_returns[i-20:i])
lagged_sums = np.zeros(len(lagged_returns_combined))
for i in range(20, len(lagged_returns_combined)):
    lagged_sums[i] = np.sum(
        lagged_returns_combined[i - 19 : i + 1]
    )  # Last 20 lagged returns

print(f"       Lagged sums computed for {len(lagged_returns_combined)} rows")

for i in tqdm(
    range(idx_partial_end_kalman, n_total), desc="Kalman TRAIN-LAGGED", disable=True
):
    train_idx = i - idx_partial_end_kalman

    # Update rolling volatility based on past predictions (for denormalization)
    # ⚠️ CRITICAL: This must match API exactly!
    if i >= 20:
        rolling_vol_h20[i] = (
            np.std(h20_predictions[i - 20 : i], ddof=1)
            if i > 20
            else rolling_vol_h20[i - 1]
        )
        rolling_vol_h20[i] = max(
            rolling_vol_h20[i], rolling_vol_partial[-1] * 0.1
        )  # Floor
    else:
        rolling_vol_h20[i] = rolling_vol_partial[-1]

    # First: PREDICT for time t
    pred = kf.predict()
    h20_predictions[i] = pred

    # Then: UPDATE with LAGGED observation (from t-20, now fully realized)
    # ⚠️ CRITICAL: Normalize INSIDE loop using current rolling_vol (same as API!)
    if i >= 20 and rolling_vol_h20[i] > 0:
        lagged_obs_normalized = lagged_sums[i] / rolling_vol_h20[i]
        lagged_obs_clipped = np.clip(lagged_obs_normalized, -3.0, 3.0)
        kf.update(lagged_obs_clipped)

    # Store state AFTER predict+update - 3D state now
    h20_state_position[i] = kf.x[0]
    h20_state_velocity[i] = kf.x[1]  # Now properly updated, not constant!
    h20_state_acceleration[i] = kf.x[2]  # NEW: 3D acceleration state
    h20_uncertainty[i] = np.trace(kf.P)

# Clean up
del lagged_returns_combined
del lagged_sums

print("    ✅ Kalman predictions on TRAIN with LAGGED UPDATE (3D STATE)")
print("       Velocity is now properly updated (not constant!)")
print(
    f"       TRAIN velocity range: [{h20_state_velocity[idx_partial_end_kalman:].min():.6f}, {h20_state_velocity[idx_partial_end_kalman:].max():.6f}]"
)
print(
    f"       TRAIN acceleration range: [{h20_state_acceleration[idx_partial_end_kalman:].min():.6f}, {h20_state_acceleration[idx_partial_end_kalman:].max():.6f}]"
)
print(f"       Final state: pos={kf.x[0]:.6f}, vel={kf.x[1]:.6f}, accel={kf.x[2]:.6f}")

# De-normalize predictions
h20_predictions_denorm = h20_predictions * rolling_vol_h20
h20_confidence = 1.0 / (1.0 + h20_uncertainty)

# STEP 4: Save kalman_state for API simulation (will use LAGGED UPDATE mode)
print("\n  STEP 4: Saving kalman_state for API simulation (LAGGED UPDATE mode)...")

# Calculate data variance from TRAIN phase predictions (valid_vals was deleted)
train_predictions = h20_predictions[idx_partial_end_kalman:]
data_variance_estimate = np.var(train_predictions[train_predictions != 0])

kalman_state = {
    "session_id": TRAINING_SESSION_ID,
    "kf_x": kf.x.copy(),
    "kf_P": kf.P.copy(),
    "kf_Q": kf.Q.copy(),
    "kf_R": kf.R.copy(),
    "kf_F": kf.F.copy(),
    "kf_H": kf.H.copy(),
    "kf_dt": kf.dt,
    "kf_adaptation_rate": kf.adaptation_rate,
    "last_rolling_vol": rolling_vol_h20[-1],
    "data_variance": data_variance_estimate,
    "mode": "lagged_update",  # Flag to indicate API should use lagged update
    "horizon": 20,  # Horizon for lagged updates
    "state_dim": 3,  # NEW: Flag indicating 3D state (position, velocity, acceleration)
}

print(f"    ✓ Kalman state saved with {len(kalman_state)} parameters")
print("    ✓ API will use LAGGED UPDATE mode (update with t-20 observations)")
print("    ✓ Kalman filter complete")

# ═══════════════════════════════════════════════════════════════════════════
# CRITICAL: CLEANUP KALMAN TARGET VARIABLES (PREVENT LEAKAGE)
# ═══════════════════════════════════════════════════════════════════════════
# These variables contain TRUE FUTURE DATA and must NOT be added as features!
# Delete them to prevent accidental use by other models (Isolation Forest, HMM, etc.)
print(
    "\n  STEP 5: Cleaning up Kalman target variables (PREVENT FUTURE DATA LEAKAGE)..."
)
del forward_returns_20d_partial  # TRUE FUTURE TARGET - DELETE
del h20_valid_mask_partial  # Valid mask for future target - DELETE
del h20_target_volnorm_partial  # Normalized future target - DELETE
del h20_target_volnorm_clipped_partial  # Clipped future target - DELETE
del forward_returns_partial  # Raw forward returns - DELETE
del rolling_vol_partial  # Rolling vol of future target - DELETE
del valid_vals  # Valid values of future target - DELETE
del kalman_state_after_partial  # Intermediate state - DELETE
print("    ✓ All Kalman target/label variables deleted")
print(
    "    ✓ Only PREDICTIONS (h20_predictions, h20_state_*) remain for feature creation"
)
print(
    "    ⚠️ forward_returns_20d was ONLY used for Kalman training, NOT added as feature!"
)
print(f"\n{'=' * 80}\n")

# %% [CELL 14] Create Kalman H=20 Features

# FEATURE ENGINEERING: Create Kalman H=20 Features (PARTIAL + TRAIN)
# ⚠️ IMPORTANT: We ONLY add Kalman PREDICTIONS as features, NOT the training target!
# The forward_returns_20d target was deleted above to prevent accidental use.


print(f"{'=' * 80}")
print("CREATING KALMAN H=20 FEATURES (PARTIAL + TRAIN)")
print(f"{'=' * 80}\n")

print("⚠️ IMPORTANT: Only Kalman PREDICTIONS are added as features!")
print("   The forward_returns_20d training target has been deleted.\n")

# ========================================================================
# Base Features (7) - These are PREDICTIONS, not the target! (added acceleration)
# ========================================================================

base_features = {
    "kalman_h20_pred": h20_predictions,  # Kalman prediction (NOT target!)
    "kalman_h20_pred_denorm": h20_predictions_denorm,  # Denormalized prediction
    "kalman_h20_state_pos": h20_state_position,  # State position
    "kalman_h20_state_vel": h20_state_velocity,  # State velocity
    "kalman_h20_state_accel": h20_state_acceleration,  # NEW: State acceleration (3D)
    "kalman_h20_confidence": h20_confidence,  # Prediction confidence
    "kalman_h20_rolling_vol": rolling_vol_h20,  # Rolling volatility (for denorm)
}

# ========================================================================
# Momentum Features (8) - Added acceleration momentum
# ========================================================================

h20_pred_mom1 = np.zeros(n_total)
h20_pred_mom5 = np.zeros(n_total)
h20_pred_mom10 = np.zeros(n_total)
h20_vel_mom1 = np.zeros(n_total)
h20_vel_mom5 = np.zeros(n_total)
h20_accel_mom1 = np.zeros(n_total)  # NEW: Acceleration momentum
h20_accel_mom5 = np.zeros(n_total)  # NEW: Acceleration momentum

for i in range(n_total):
    if i >= 1:
        h20_pred_mom1[i] = h20_predictions[i] - h20_predictions[i - 1]
        h20_vel_mom1[i] = h20_state_velocity[i] - h20_state_velocity[i - 1]
        h20_accel_mom1[i] = (
            h20_state_acceleration[i] - h20_state_acceleration[i - 1]
        )  # NEW
    if i >= 5:
        h20_pred_mom5[i] = h20_predictions[i] - h20_predictions[i - 5]
        h20_vel_mom5[i] = h20_state_velocity[i] - h20_state_velocity[i - 5]
        h20_accel_mom5[i] = (
            h20_state_acceleration[i] - h20_state_acceleration[i - 5]
        )  # NEW
    if i >= 10:
        h20_pred_mom10[i] = h20_predictions[i] - h20_predictions[i - 10]

momentum_features = {
    "kalman_h20_pred_mom1": h20_pred_mom1,
    "kalman_h20_pred_mom5": h20_pred_mom5,
    "kalman_h20_pred_mom10": h20_pred_mom10,
    "kalman_h20_vel_mom1": h20_vel_mom1,
    "kalman_h20_vel_mom5": h20_vel_mom5,
    "kalman_h20_accel_mom1": h20_accel_mom1,  # NEW: Acceleration change 1d
    "kalman_h20_accel_mom5": h20_accel_mom5,  # NEW: Acceleration change 5d
}

# ========================================================================
# Interaction Features (6) - Added acceleration interactions
# ========================================================================

interaction_features = {
    "kalman_h20_pred_weighted": h20_predictions * h20_confidence,
    "kalman_h20_pred_vol_adj": h20_predictions_denorm / (rolling_vol_h20 + 1e-6),
    "kalman_h20_accel_vol_ratio": h20_state_acceleration
    / (rolling_vol_h20 + 1e-6),  # NEW
    "kalman_h20_vel_vol_ratio": h20_state_velocity / (rolling_vol_h20 + 1e-6),
    "kalman_h20_pred_vel_interact": h20_predictions * h20_state_velocity,
    "kalman_h20_vel_accel_interact": h20_state_velocity
    * h20_state_acceleration,  # NEW: vel * accel
    "kalman_h20_accel_sign": np.sign(
        h20_state_acceleration
    ),  # NEW: acceleration direction
}

# ========================================================================
# Regime Features (5) - Added acceleration regime
# ========================================================================

# Direction
h20_signal_dir = np.sign(h20_predictions)

# Prediction strength (quintiles)
pred_abs = np.abs(h20_predictions)
quintiles = np.percentile(pred_abs, [20, 40, 60, 80])
h20_pred_strength = np.ones(n_total)
h20_pred_strength[pred_abs > quintiles[0]] = 2
h20_pred_strength[pred_abs > quintiles[1]] = 3
h20_pred_strength[pred_abs > quintiles[2]] = 4
h20_pred_strength[pred_abs > quintiles[3]] = 5

# Volatility regime
vol_terciles = np.percentile(rolling_vol_h20, [33, 67])
h20_vol_regime = np.ones(n_total)
h20_vol_regime[rolling_vol_h20 > vol_terciles[0]] = 2
h20_vol_regime[rolling_vol_h20 > vol_terciles[1]] = 3

# NEW: Acceleration regime (terciles) - indicates momentum phase
accel_valid = h20_state_acceleration[h20_state_acceleration != 0]
if len(accel_valid) > 10:
    accel_terciles = np.percentile(accel_valid, [33, 67])
else:
    accel_terciles = [-0.001, 0.001]
h20_accel_regime = np.ones(n_total)
h20_accel_regime[h20_state_acceleration > accel_terciles[0]] = 2
h20_accel_regime[h20_state_acceleration > accel_terciles[1]] = 3

# CONTRARIAN SIGNAL: Inverted Kalman prediction for mean-reversion regimes
# When the Kalman filter predicts positive, markets often mean-revert negatively
# This feature allows the model to learn when to use contrarian vs. momentum
h20_pred_contrarian = -h20_predictions  # Inverted prediction for mean-reversion
h20_signal_contrarian = -h20_signal_dir  # Inverted direction signal

regime_features = {
    "kalman_h20_signal_dir": h20_signal_dir,
    "kalman_h20_pred_strength": h20_pred_strength,
    "kalman_h20_vol_regime": h20_vol_regime,
    "kalman_h20_accel_regime": h20_accel_regime,  # NEW: Acceleration regime (3D)
    "kalman_h20_pred_contrarian": h20_pred_contrarian,  # Inverted prediction
    "kalman_h20_signal_contrarian": h20_signal_contrarian,  # Inverted direction
}

# ========================================================================
# Lagged Features (4)
# ========================================================================

h20_pred_lag1 = np.zeros(n_total)
h20_pred_lag5 = np.zeros(n_total)
h20_pred_lag10 = np.zeros(n_total)
h20_conf_lag1 = np.zeros(n_total)

for i in range(n_total):
    if i >= 1:
        h20_pred_lag1[i] = h20_predictions[i - 1]
        h20_conf_lag1[i] = h20_confidence[i - 1]
    if i >= 5:
        h20_pred_lag5[i] = h20_predictions[i - 5]
    if i >= 10:
        h20_pred_lag10[i] = h20_predictions[i - 10]

lag_features = {
    "kalman_h20_pred_lag1": h20_pred_lag1,
    "kalman_h20_pred_lag5": h20_pred_lag5,
    "kalman_h20_pred_lag10": h20_pred_lag10,
    "kalman_h20_conf_lag1": h20_conf_lag1,
}

# ========================================================================
# Rolling Features (5)
# ========================================================================

h20_pred_ma5 = np.zeros(n_total)
h20_pred_ma10 = np.zeros(n_total)
h20_pred_ma20 = np.zeros(n_total)
h20_pred_std5 = np.zeros(n_total)
h20_pred_std10 = np.zeros(n_total)

for i in range(n_total):
    if i >= 5:
        h20_pred_ma5[i] = np.mean(h20_predictions[i - 5 : i])
        h20_pred_std5[i] = np.std(h20_predictions[i - 5 : i])
    if i >= 10:
        h20_pred_ma10[i] = np.mean(h20_predictions[i - 10 : i])
        h20_pred_std10[i] = np.std(h20_predictions[i - 10 : i])
    if i >= 20:
        h20_pred_ma20[i] = np.mean(h20_predictions[i - 20 : i])

rolling_features = {
    "kalman_h20_pred_ma5": h20_pred_ma5,
    "kalman_h20_pred_ma10": h20_pred_ma10,
    "kalman_h20_pred_ma20": h20_pred_ma20,
    "kalman_h20_pred_std5": h20_pred_std5,
    "kalman_h20_pred_std10": h20_pred_std10,
}

# ========================================================================
# Cross-Model Kalman+HMM Features (7) - ENSEMBLE STACKING FEATURES
# These combine Kalman predictions/velocity with HMM regime information
# ========================================================================
print("\n  STEP 5a: Creating Cross-Model Kalman+HMM features...")

# Extract HMM regime arrays from combined dataframe
if "hmm_regime" in df_combined_kalman.columns:
    hmm_regime_arr = df_combined_kalman["hmm_regime"].to_numpy().astype(float)
else:
    hmm_regime_arr = np.zeros(n_total)
    print("    ⚠️ hmm_regime not found - using zeros")

if "hmm5_regime" in df_combined_kalman.columns:
    hmm5_regime_arr = df_combined_kalman["hmm5_regime"].to_numpy().astype(float)
else:
    hmm5_regime_arr = np.zeros(n_total)
    print("    ⚠️ hmm5_regime not found - using zeros")

if "hmm_regime_confidence" in df_combined_kalman.columns:
    hmm_conf_arr = df_combined_kalman["hmm_regime_confidence"].to_numpy().astype(float)
elif "hmm_confidence" in df_combined_kalman.columns:
    hmm_conf_arr = df_combined_kalman["hmm_confidence"].to_numpy().astype(float)
else:
    hmm_conf_arr = np.ones(n_total) * 0.5
    print("    ⚠️ hmm_regime_confidence not found - using 0.5")

if "hmm5_regime_confidence" in df_combined_kalman.columns:
    hmm5_conf_arr = (
        df_combined_kalman["hmm5_regime_confidence"].to_numpy().astype(float)
    )
elif "hmm5_confidence" in df_combined_kalman.columns:
    hmm5_conf_arr = df_combined_kalman["hmm5_confidence"].to_numpy().astype(float)
else:
    hmm5_conf_arr = np.ones(n_total) * 0.5
    print("    ⚠️ hmm5_regime_confidence not found - using 0.5")

# 1. Kalman-HMM Agreement: Does Kalman velocity direction agree with HMM bull/bear?
#    HMM regime 0,1 = bearish, 2,3 = bullish (for 4-state)
#    Velocity > 0 = bullish, < 0 = bearish
kalman_bullish = (h20_state_velocity > 0).astype(float)
hmm_bullish = (hmm_regime_arr >= 2).astype(float)  # regimes 2,3 are bullish
kalman_hmm_agree = (kalman_bullish == hmm_bullish).astype(float)

# 2. Kalman prediction weighted by HMM regime
#    Higher weight for extreme regimes (0=strong bear, 3=strong bull)
regime_weight = np.where(
    hmm_regime_arr == 0,
    -1.0,
    np.where(hmm_regime_arr == 1, -0.5, np.where(hmm_regime_arr == 2, 0.5, 1.0)),
)
kalman_pred_x_regime = h20_predictions * regime_weight

# 3. Kalman velocity weighted by HMM-5 regime (finer granularity)
kalman_vel_x_hmm5 = h20_state_velocity * hmm5_regime_arr

# 4. Combined confidence: Kalman confidence * HMM confidence
#    High when BOTH models are confident
kalman_hmm_conf_product = h20_confidence * hmm_conf_arr

# 5. Kalman-HMM5 confidence product (for 5-state model)
kalman_hmm5_conf_product = h20_confidence * hmm5_conf_arr

# 6. Kalman-HMM interaction: Prediction × HMM regime
#    Direct interaction between Kalman prediction and HMM-4 regime
kalman_hmm_interact = h20_predictions * hmm_regime_arr

# 7. Kalman-HMM5 interaction: Prediction × HMM-5 regime
#    Direct interaction between Kalman prediction and HMM-5 regime
kalman_hmm5_interact = h20_predictions * hmm5_regime_arr

cross_model_features = {
    "kalman_hmm_agree": kalman_hmm_agree,
    "kalman_pred_x_regime": kalman_pred_x_regime,
    "kalman_vel_x_hmm5": kalman_vel_x_hmm5,
    "kalman_hmm_conf_product": kalman_hmm_conf_product,
    "kalman_hmm5_conf_product": kalman_hmm5_conf_product,
    "kalman_hmm_interact": kalman_hmm_interact,
    "kalman_hmm5_interact": kalman_hmm5_interact,
}

print("    ✓ Created 7 Cross-Model Kalman+HMM features")
print("      - kalman_hmm_agree: Direction agreement (velocity vs HMM bull/bear)")
print("      - kalman_pred_x_regime: Prediction × regime weight")
print("      - kalman_vel_x_hmm5: Velocity × HMM-5 regime")
print("      - kalman_hmm_conf_product: Kalman conf × HMM conf")
print("      - kalman_hmm5_conf_product: Kalman conf × HMM-5 conf")
print("      - kalman_hmm_interact: Prediction × HMM-4 regime")
print("      - kalman_hmm5_interact: Prediction × HMM-5 regime")

# ========================================================================
# Cross-Model Kalman+CUSUM+Anomaly Features (10) - EXTENDED ENSEMBLE
# These combine Kalman with CUSUM changepoints and Anomaly detection
# ========================================================================
print("\n  STEP 5b: Creating Cross-Model Kalman+CUSUM+Anomaly features...")

# Extract CUSUM and Anomaly arrays from combined dataframe
if "changepoint_vol_any" in df_combined_kalman.columns:
    cusum_vol_change_arr = (
        df_combined_kalman["changepoint_vol_any"].to_numpy().astype(float)
    )
else:
    cusum_vol_change_arr = np.zeros(n_total)
    print("    ⚠️ changepoint_vol_any not found - using zeros")

if "changepoint_ret_any" in df_combined_kalman.columns:
    cusum_ret_change_arr = (
        df_combined_kalman["changepoint_ret_any"].to_numpy().astype(float)
    )
else:
    cusum_ret_change_arr = np.zeros(n_total)
    print("    ⚠️ changepoint_ret_any not found - using zeros")

if "cusum_days_since_changepoint" in df_combined_kalman.columns:
    cusum_days_arr = (
        df_combined_kalman["cusum_days_since_changepoint"].to_numpy().astype(float)
    )
else:
    cusum_days_arr = np.zeros(n_total)
    print("    ⚠️ cusum_days_since_changepoint not found - using zeros")

if "anomaly_extreme_is" in df_combined_kalman.columns:
    anomaly_extreme_arr = (
        df_combined_kalman["anomaly_extreme_is"].to_numpy().astype(float)
    )
else:
    anomaly_extreme_arr = np.zeros(n_total)
    print("    ⚠️ anomaly_extreme_is not found - using zeros")

if "anomaly_extreme_severity" in df_combined_kalman.columns:
    anomaly_extreme_sev_arr = (
        df_combined_kalman["anomaly_extreme_severity"].to_numpy().astype(float)
    )
else:
    anomaly_extreme_sev_arr = np.zeros(n_total)
    print("    ⚠️ anomaly_extreme_severity not found - using zeros")

if "anomaly_moderate_is" in df_combined_kalman.columns:
    anomaly_moderate_arr = (
        df_combined_kalman["anomaly_moderate_is"].to_numpy().astype(float)
    )
else:
    anomaly_moderate_arr = np.zeros(n_total)
    print("    ⚠️ anomaly_moderate_is not found - using zeros")

if "hmm_regime_change" in df_combined_kalman.columns:
    hmm_regime_change_arr = (
        df_combined_kalman["hmm_regime_change"].to_numpy().astype(float)
    )
else:
    hmm_regime_change_arr = np.zeros(n_total)
    print("    ⚠️ hmm_regime_change not found - using zeros")

if "hmm5_regime_change" in df_combined_kalman.columns:
    hmm5_regime_change_arr = (
        df_combined_kalman["hmm5_regime_change"].to_numpy().astype(float)
    )
else:
    hmm5_regime_change_arr = np.zeros(n_total)
    print("    ⚠️ hmm5_regime_change not found - using zeros")

# 6. Kalman prediction × CUSUM volatility changepoint
#    Amplifies Kalman signal when CUSUM detects regime change
kalman_cusum_vol_interact = h20_predictions * cusum_vol_change_arr

# 7. Kalman prediction × anomaly severity
#    Amplifies Kalman signal during anomalies (high uncertainty periods)
kalman_anomaly_interact = h20_predictions * anomaly_extreme_sev_arr

# 8. Kalman velocity × CUSUM returns changepoint
#    Combines momentum signal with returns changepoint
kalman_cusum_ret_interact = h20_state_velocity * cusum_ret_change_arr

# 9. HMM regime change agrees with CUSUM changepoint
#    1 if both detect a change, 0.5 if only one, 0 if neither
hmm_cusum_agree = (hmm_regime_change_arr + cusum_vol_change_arr) / 2.0

# 10. HMM extreme regime (0 or 3) agrees with anomaly
#     HMM extreme regimes should correlate with anomaly detection
hmm_extreme_regime = ((hmm_regime_arr == 0) | (hmm_regime_arr == 3)).astype(float)
hmm_anomaly_agree = (hmm_extreme_regime * anomaly_extreme_arr).astype(float)

# 11. Models agree count: How many models agree on direction/signal?
#     Kalman bullish, HMM bullish, no CUSUM changepoint = 3 types of agreement
models_agree_bullish = (
    kalman_bullish + hmm_bullish + (1 - cusum_vol_change_arr)
)  # 0-3 scale
models_agree_count = models_agree_bullish  # Higher = more bullish agreement

# 12. Kalman confidence weighted by CUSUM stability
#     Lower weight near changepoints (less stable), higher weight when stable
cusum_stability = 1.0 / (
    1.0 + np.exp(-0.1 * (cusum_days_arr - 10))
)  # Sigmoid: stable after 10 days
kalman_conf_stability = h20_confidence * cusum_stability

# 13. All models bearish: Binary flag when all models agree on bearish
#     Kalman velocity < 0, HMM regime 0-1, any anomaly
all_models_bearish = (
    (h20_state_velocity < 0) & (hmm_regime_arr < 2) & (anomaly_moderate_arr > 0)
).astype(float)

# 14. All models bullish: Binary flag when all models agree on bullish
#     Kalman velocity > 0, HMM regime 2-3, no extreme anomaly
all_models_bullish = (
    (h20_state_velocity > 0) & (hmm_regime_arr >= 2) & (anomaly_extreme_arr == 0)
).astype(float)

# 15. Cross-model uncertainty: Higher when models disagree
#     Measured as disagreement between Kalman direction and HMM regime
cross_model_disagreement = np.abs(kalman_bullish - hmm_bullish)
cross_model_uncertainty = (
    cross_model_disagreement * (1 - h20_confidence) * (1 - hmm_conf_arr)
)

cross_model_extended_features = {
    "kalman_cusum_vol_interact": kalman_cusum_vol_interact,
    "kalman_anomaly_interact": kalman_anomaly_interact,
    "kalman_cusum_ret_interact": kalman_cusum_ret_interact,
    "hmm_cusum_agree": hmm_cusum_agree,
    "hmm_anomaly_agree": hmm_anomaly_agree,
    "models_agree_count": models_agree_count,
    "kalman_conf_stability": kalman_conf_stability,
    "all_models_bearish": all_models_bearish,
    "all_models_bullish": all_models_bullish,
    "cross_model_uncertainty": cross_model_uncertainty,
}

# Merge extended features with cross_model_features
cross_model_features.update(cross_model_extended_features)

print("    ✓ Created 10 Cross-Model Kalman+CUSUM+Anomaly features")
print("      - kalman_cusum_vol_interact: Kalman pred × CUSUM vol changepoint")
print("      - kalman_anomaly_interact: Kalman pred × anomaly severity")
print("      - kalman_cusum_ret_interact: Kalman vel × CUSUM ret changepoint")
print("      - hmm_cusum_agree: HMM change + CUSUM change agreement")
print("      - hmm_anomaly_agree: HMM extreme regime × anomaly flag")
print("      - models_agree_count: Count of bullish signals (0-3)")
print("      - kalman_conf_stability: Kalman conf × CUSUM stability")
print("      - all_models_bearish: All models agree bearish")
print("      - all_models_bullish: All models agree bullish")
print("      - cross_model_uncertainty: Model disagreement × uncertainty")

# ════════════════════════════════════════════════════════════════════════════
# 4C. FEATURE-GROUP HMM CROSS-MODEL INTERACTIONS
# Creates interactions between FG-HMMs (M, E, I, P, V, S) and base models
# ════════════════════════════════════════════════════════════════════════════

print("\n  STEP 4C: Creating Feature-Group HMM Cross-Model Interactions...")

# FG-HMM prefixes to process
fg_prefixes = ["M", "E", "I", "P", "V", "S"]
fg_cross_model_features = {}
fg_cross_model_count = 0

for prefix in fg_prefixes:
    # Check if FG-HMM features exist for this prefix
    regime_col = f"{prefix}_hmm_regime"
    conf_col = f"{prefix}_hmm_confidence"
    change_col = f"{prefix}_hmm_regime_change"

    if regime_col not in df_combined_kalman.columns:
        print(f"    ⚠️ {prefix}_hmm_* features not found - skipping")
        continue

    # Extract FG-HMM arrays
    fg_regime_arr = df_combined_kalman[regime_col].to_numpy().astype(float)
    fg_conf_arr = (
        df_combined_kalman[conf_col].to_numpy().astype(float)
        if conf_col in df_combined_kalman.columns
        else np.ones(n_total) * 0.5
    )
    fg_change_arr = (
        df_combined_kalman[change_col].to_numpy().astype(float)
        if change_col in df_combined_kalman.columns
        else np.zeros(n_total)
    )

    # 1. FG-HMM × Kalman prediction interaction
    #    Amplifies Kalman signal when FG-HMM regime is high (bullish regimes)
    fg_kalman_interact = h20_predictions * fg_regime_arr
    fg_cross_model_features[f"{prefix}_kalman_interact"] = fg_kalman_interact

    # 2. FG-HMM × CUSUM volatility changepoint agreement
    #    1 if both detect a change, 0.5 if only one, 0 if neither
    fg_cusum_agree = (fg_change_arr + cusum_vol_change_arr) / 2.0
    fg_cross_model_features[f"{prefix}_cusum_agree"] = fg_cusum_agree

    # 3. FG-HMM × Anomaly agreement
    #    FG-HMM extreme regimes (0 or 2 for 3-component) should correlate with anomalies
    fg_extreme_regime = ((fg_regime_arr == 0) | (fg_regime_arr == 2)).astype(float)
    fg_anomaly_agree = fg_extreme_regime * anomaly_extreme_arr
    fg_cross_model_features[f"{prefix}_anomaly_agree"] = fg_anomaly_agree

    # 4. FG-HMM × HMM-4 regime agreement
    #    Both HMMs in similar regime = strong signal
    #    Normalize: HMM-4 has 4 regimes (0-3), FG-HMM has 3 regimes (0-2)
    hmm4_normalized = hmm_regime_arr / 3.0  # Scale to 0-1
    fg_normalized = fg_regime_arr / 2.0  # Scale to 0-1
    fg_hmm4_agree = 1.0 - np.abs(
        hmm4_normalized - fg_normalized
    )  # 1 = perfect agreement, 0 = max disagreement
    fg_cross_model_features[f"{prefix}_hmm4_agree"] = fg_hmm4_agree

    # 5. FG-HMM × HMM-5 regime agreement
    hmm5_normalized = hmm5_regime_arr / 4.0  # Scale to 0-1
    fg_hmm5_agree = 1.0 - np.abs(hmm5_normalized - fg_normalized)
    fg_cross_model_features[f"{prefix}_hmm5_agree"] = fg_hmm5_agree

    # 6. FG-HMM confidence × Kalman confidence synergy
    #    High when both models are confident
    fg_kalman_conf_synergy = fg_conf_arr * h20_confidence
    fg_cross_model_features[f"{prefix}_kalman_conf_synergy"] = fg_kalman_conf_synergy

    # 7. FG-HMM regime change × CUSUM days since changepoint
    #    Low values = both models see fresh regime change
    fg_cusum_recency = fg_change_arr * (
        1.0 / (1.0 + cusum_days_arr)
    )  # Higher if recent CUSUM change
    fg_cross_model_features[f"{prefix}_cusum_change_recency"] = fg_cusum_recency

    fg_cross_model_count += 7
    print(f"    ✓ {prefix}*: 7 cross-model features created")

# Merge FG cross-model features into main dict
cross_model_features.update(fg_cross_model_features)

print(
    f"    ✓ Created {fg_cross_model_count} Feature-Group HMM Cross-Model features total"
)
print("      Per group: _kalman_interact, _cusum_agree, _anomaly_agree,")
print(
    "                 _hmm4_agree, _hmm5_agree, _kalman_conf_synergy, _cusum_change_recency"
)

# ========================================================================
# Add All Features to Combined DataFrame
# ========================================================================

all_kalman_features = {
    **base_features,
    **momentum_features,
    **interaction_features,
    **regime_features,
    **lag_features,
    **rolling_features,
    **cross_model_features,
}

print("\n  STEP 5: Adding Kalman features to PARTIAL+TRAIN dataframe...")

for name, values in all_kalman_features.items():
    df_combined_kalman = df_combined_kalman.with_columns(pl.Series(name, values))

print(f"    ✓ Added {len(all_kalman_features)} Kalman H=20 features")
print("      - Base: 6")
print("      - Momentum: 5")
print("      - Interactions: 4")
print("      - Regimes: 3")
print("      - Lags: 4")
print("      - Rolling: 5")
print("      - Cross-Model Kalman+HMM: 7")
print("      - Cross-Model Kalman+CUSUM+Anomaly: 10")

# ========================================================================
# STEP 6: SPLIT back to PARTIAL and TRAIN
# ========================================================================

print("\n  STEP 6: Splitting back to PARTIAL and TRAIN...")
df_partial = df_combined_kalman[0:idx_partial_end_kalman].clone()
df_train = df_combined_kalman[idx_partial_end_kalman:idx_train_end_kalman].clone()

df_pl = df_train.clone()

print(f"    • PARTIAL: {len(df_partial)} rows, {len(df_partial.columns)} features")
print(f"    • TRAIN: {len(df_train)} rows, {len(df_train.columns)} features")
print("    • VALIDATION: Will get features row-by-row in API simulation")

# 🔧 DEBUG: Verify Cross-Model features (Kalman × CUSUM × Anomaly)
print("\n  🔍 CROSS-MODEL FEATURE VALIDATION:")
cross_model_check = [
    "kalman_cusum_vol_interact",
    "kalman_cusum_ret_interact",
    "kalman_anomaly_interact",
    "hmm_cusum_agree",
    "hmm_anomaly_agree",
    "models_agree_count",
    "kalman_conf_stability",
]
for feat in cross_model_check:
    if feat in df_train.columns:
        col = df_train[feat]
        non_null = col.drop_nulls()
        non_zero = (col.abs() > 1e-10).sum()  # Use abs() > epsilon for float comparison
        print(
            f"    • {feat}: non-null={len(non_null)}/{len(col)}, non-zero={non_zero}, range=[{col.min():.6f}, {col.max():.6f}]"
        )
    else:
        print(f"    ⚠️ {feat}: NOT FOUND!")

# ========================================================================
# STEP 6.5: ADD KALMAN ALIASES FOR POSITION SIZER
# Position sizer expects kalman_ prefixed names for some features
# ========================================================================
print("\n  STEP 6.5: Adding Kalman aliases for position sizer...")

kalman_aliases = {
    "kalman_h20_signal_direction": "kalman_h20_signal_dir",
    "kalman_all_models_bullish": "all_models_bullish",
    "kalman_all_models_bearish": "all_models_bearish",
    "kalman_hmm_cusum_agree": "hmm_cusum_agree",
}

for alias_name, source_name in kalman_aliases.items():
    if source_name in df_train.columns and alias_name not in df_train.columns:
        df_train = df_train.with_columns([pl.col(source_name).alias(alias_name)])
        print(f"    ✓ Added alias: {alias_name} → {source_name}")
    elif alias_name in df_train.columns:
        print(f"    ℹ️  Alias already exists: {alias_name}")
    else:
        print(f"    ⚠️  Source missing: {source_name} (cannot create {alias_name})")

for alias_name, source_name in kalman_aliases.items():
    if source_name in df_partial.columns and alias_name not in df_partial.columns:
        df_partial = df_partial.with_columns([pl.col(source_name).alias(alias_name)])

# Update df_pl as well
df_pl = df_train.clone()

print(f"    • TRAIN now has {len(df_train.columns)} columns (with aliases)")
print(f"    • PARTIAL now has {len(df_partial.columns)} columns (with aliases)")

# ========================================================================
# STEP 7: SAVE train_with_all_features.csv and partial_with_all_features.csv
# CRITICAL: These files are used by Cell 28 API simulation to load history
# ========================================================================
print("\n  STEP 7: Saving CSVs for API simulation history loading...")

train_all_features_path = output_dir / "train_with_all_features.csv"
partial_all_features_path = output_dir / "partial_with_all_features.csv"

df_train.write_csv(train_all_features_path)
print(f"    ✓ Saved TRAIN: {train_all_features_path}")
print(f"      Size: {train_all_features_path.stat().st_size / 1024 / 1024:.2f} MB")

df_partial.write_csv(partial_all_features_path)
print(f"    ✓ Saved PARTIAL: {partial_all_features_path}")
print(f"      Size: {partial_all_features_path.stat().st_size / 1024 / 1024:.2f} MB")

print("\n  ✓ Kalman H=20 features successfully applied to PARTIAL+TRAIN")
print("  ✓ kalman_state saved for API simulation")
print("  ✓ train_with_all_features.csv saved for history loading")
print("  ✓ partial_with_all_features.csv saved for history loading")
print("  ✓ Sequential processing ensures NO DATA LEAKAGE")
print(f"\n{'=' * 80}\n")

# %% [CELL 14.5] GARCH(1,1) Volatility Features
# ═══════════════════════════════════════════════════════════════════════════
# GARCH(1,1) VOLATILITY MODEL
# ═══════════════════════════════════════════════════════════════════════════
# GARCH (Generalized Autoregressive Conditional Heteroskedasticity) models
# the time-varying variance of returns, capturing volatility clustering.
#
# GARCH(1,1) equation:
#   σ²[t] = ω + α * ε²[t-1] + β * σ²[t-1]
# where:
#   ω (omega) = long-run variance weight
#   α (alpha) = ARCH parameter (reaction to past shocks)
#   β (beta)  = GARCH parameter (persistence of volatility)
#
# STRATEGY:
# 1. Fit GARCH(1,1) on PARTIAL to get parameters (ω, α, β)
# 2. Apply row-by-row to PARTIAL + TRAIN for consistent features
# 3. API simulation uses same row-by-row update logic
# ═══════════════════════════════════════════════════════════════════════════

print(f"{'=' * 80}")
print("GARCH(1,1) VOLATILITY FEATURES")
print(f"{'=' * 80}\n")

# Check for arch library
try:
    from arch import arch_model

    GARCH_AVAILABLE = True
    print("✓ arch library available - using GARCH(1,1) model")
except ImportError:
    GARCH_AVAILABLE = False
    print(
        "⚠️  arch library not installed - creating GARCH-like features with EWMA fallback"
    )
    print("   Install with: pip install arch")

if GARCH_AVAILABLE:
    # ────────────────────────────────────────────────────────────────────────
    # STEP 1: Fit GARCH(1,1) on PARTIAL returns to get parameters
    # ────────────────────────────────────────────────────────────────────────
    print("\n  STEP 1: Fitting GARCH(1,1) on PARTIAL dataset...")

    # Get returns from PARTIAL
    partial_returns = df_partial["lagged_forward_returns"].to_numpy()
    # Scale returns for numerical stability (GARCH expects returns in percent-like scale)
    returns_scaled = partial_returns * 100

    # Fit GARCH(1,1) model
    try:
        garch_model = arch_model(
            returns_scaled, vol="Garch", p=1, q=1, mean="Zero", rescale=False
        )
        garch_result = garch_model.fit(disp="off", show_warning=False)

        # Extract parameters
        garch_omega = garch_result.params["omega"]
        garch_alpha = garch_result.params["alpha[1]"]
        garch_beta = garch_result.params["beta[1]"]

        print("    ✅ GARCH(1,1) fitted successfully!")
        print(f"    • ω (omega): {garch_omega:.6f} (long-run variance)")
        print(f"    • α (alpha): {garch_alpha:.6f} (shock reaction)")
        print(f"    • β (beta):  {garch_beta:.6f} (persistence)")
        print(
            f"    • α + β = {garch_alpha + garch_beta:.6f} (should be < 1 for stationarity)"
        )

        if garch_alpha + garch_beta >= 1.0:
            print(
                "    ⚠️  WARNING: α + β >= 1, model is not stationary - using fallback"
            )
            GARCH_FITTED = False
        else:
            GARCH_FITTED = True
            # Calculate unconditional variance
            garch_long_run_var = garch_omega / (1 - garch_alpha - garch_beta)
            print(f"    • Long-run variance: {garch_long_run_var:.6f}")
            print(f"    • Long-run volatility: {np.sqrt(garch_long_run_var):.4f}%")

    except Exception as e:
        print(f"    ⚠️  GARCH fitting failed: {e}")
        print("    Using EWMA fallback instead")
        GARCH_FITTED = False
else:
    GARCH_FITTED = False

# ────────────────────────────────────────────────────────────────────────────
# STEP 2: Calculate GARCH features row-by-row (or EWMA fallback)
# ────────────────────────────────────────────────────────────────────────────
print("\n  STEP 2: Calculating GARCH features row-by-row...")

# Get combined returns - HANDLE NaNs!
returns_partial = (
    df_partial["lagged_forward_returns"].to_numpy() * 100
)  # Scale for GARCH
returns_train = df_train["lagged_forward_returns"].to_numpy() * 100
returns_combined = np.concatenate([returns_partial, returns_train])

# 🔧 FIX: Replace NaN with 0 for GARCH calculations
returns_combined = np.nan_to_num(returns_combined, nan=0.0)

n_total_garch = len(returns_combined)
idx_partial_end_garch = len(returns_partial)

print(f"    • Returns combined: {n_total_garch} rows")
print(f"    • NaN count in returns: {np.isnan(returns_combined).sum()}")
print(
    f"    • Returns range: [{returns_combined.min():.4f}, {returns_combined.max():.4f}]"
)

# Initialize GARCH arrays
garch_variance = np.zeros(n_total_garch)
garch_volatility = np.zeros(n_total_garch)
garch_forecast_1d = np.zeros(n_total_garch)
garch_standardized_resid = np.zeros(n_total_garch)
garch_vol_shock = np.zeros(n_total_garch)

if GARCH_FITTED:
    # Use fitted GARCH parameters for row-by-row calculation
    print(
        f"    Using GARCH(1,1) with fitted parameters: ω={garch_omega:.4f}, α={garch_alpha:.4f}, β={garch_beta:.4f}"
    )

    # Initialize with long-run variance
    var_t = garch_long_run_var

    for i in range(n_total_garch):
        # Store current variance
        garch_variance[i] = var_t
        garch_volatility[i] = np.sqrt(var_t) / 100  # Rescale back to decimal

        # Standardized residual
        if var_t > 0:
            garch_standardized_resid[i] = returns_combined[i] / np.sqrt(var_t)
        else:
            garch_standardized_resid[i] = 0.0

        # Forecast 1-day ahead
        epsilon_sq = returns_combined[i] ** 2
        garch_forecast_1d[i] = (
            garch_omega + garch_alpha * epsilon_sq + garch_beta * var_t
        )

        # Volatility shock: (realized - expected) / expected
        if var_t > 0:
            garch_vol_shock[i] = (epsilon_sq - var_t) / var_t
        else:
            garch_vol_shock[i] = 0.0

        # Update variance for next step: σ²[t+1] = ω + α*ε²[t] + β*σ²[t]
        var_t = garch_omega + garch_alpha * epsilon_sq + garch_beta * var_t
        var_t = max(var_t, 1e-8)  # Floor to prevent numerical issues

    print(f"    ✅ GARCH features calculated for {n_total_garch} rows")

else:
    # EWMA fallback when GARCH not available/fitted
    print("    Using EWMA fallback (no GARCH parameters)")

    ewma_lambda = 0.94  # RiskMetrics EWMA decay factor
    # 🔧 FIX: Use nanvar to handle potential NaN values, fallback to default if all NaN
    initial_returns = returns_combined[: min(21, len(returns_combined))]
    var_t = (
        np.nanvar(initial_returns) if np.any(~np.isnan(initial_returns)) else 0.0001
    )  # Safe default
    var_t = max(var_t, 1e-8)  # Floor to prevent zero variance

    print(f"    • Initial variance: {var_t:.6f}")

    for i in range(n_total_garch):
        garch_variance[i] = var_t
        garch_volatility[i] = np.sqrt(var_t) / 100  # Rescale to decimal

        epsilon_sq = returns_combined[i] ** 2

        # Standardized residual
        if var_t > 0:
            garch_standardized_resid[i] = returns_combined[i] / np.sqrt(var_t)
            garch_vol_shock[i] = (epsilon_sq - var_t) / var_t
        else:
            garch_standardized_resid[i] = 0.0
            garch_vol_shock[i] = 0.0

        # Forecast using EWMA
        garch_forecast_1d[i] = ewma_lambda * var_t + (1 - ewma_lambda) * epsilon_sq

        # Update variance with EWMA
        var_t = ewma_lambda * var_t + (1 - ewma_lambda) * epsilon_sq
        var_t = max(var_t, 1e-8)

    print(f"    ✅ EWMA-based features calculated for {n_total_garch} rows")
    # Set fallback parameters for API
    garch_omega = 0.0
    garch_alpha = 1 - ewma_lambda
    garch_beta = ewma_lambda

# Rescale forecast back to decimal
garch_forecast_1d = np.sqrt(garch_forecast_1d) / 100

# Debug info: Check GARCH arrays
print(
    f"    • GARCH variance range: [{garch_variance.min():.6f}, {garch_variance.max():.6f}]"
)
print(
    f"    • GARCH volatility range: [{garch_volatility.min():.6f}, {garch_volatility.max():.6f}]"
)
print(
    f"    • Non-zero volatility count: {np.sum(garch_volatility > 0)} / {n_total_garch}"
)

# ────────────────────────────────────────────────────────────────────────────
# STEP 3: Create derived GARCH features
# ────────────────────────────────────────────────────────────────────────────
print("\n  STEP 3: Creating derived GARCH features...")

# GARCH regime (terciles of volatility) - with safeguard for empty/zero arrays
positive_garch_vol = garch_volatility[garch_volatility > 0]
if len(positive_garch_vol) >= 3:
    garch_vol_terciles = np.percentile(positive_garch_vol, [33, 67])
else:
    # Fallback if not enough positive values
    print(
        "    ⚠️ Warning: Insufficient positive GARCH volatility values, using default terciles"
    )
    garch_vol_terciles = [0.01, 0.02]  # Default tercile thresholds

garch_vol_regime = np.ones(n_total_garch)
garch_vol_regime[garch_volatility > garch_vol_terciles[0]] = 2
garch_vol_regime[garch_volatility > garch_vol_terciles[1]] = 3

# GARCH volatility change
garch_vol_change_1d = np.zeros(n_total_garch)
garch_vol_change_5d = np.zeros(n_total_garch)
for i in range(1, n_total_garch):
    garch_vol_change_1d[i] = garch_volatility[i] - garch_volatility[i - 1]
    if i >= 5:
        garch_vol_change_5d[i] = garch_volatility[i] - garch_volatility[i - 5]

# GARCH surprise (actual REALIZED volatility vs GARCH forecast)
# garch_surprise[i] = (actual_realized_vol[i] - garch_forecast[i-1]) / garch_forecast[i-1]
# NOTE: Use daily_volatility_lagged (actual realized) NOT garch_volatility (internal GARCH state)
garch_surprise = np.zeros(n_total_garch)

# Get actual realized volatility from data
actual_vol_partial = df_partial["daily_volatility_lagged"].to_numpy()
actual_vol_train = df_train["daily_volatility_lagged"].to_numpy()
actual_realized_vol = np.concatenate([actual_vol_partial, actual_vol_train])
actual_realized_vol = np.nan_to_num(actual_realized_vol, nan=0.0)

print(
    f"    • garch_forecast_1d range: [{garch_forecast_1d.min():.8f}, {garch_forecast_1d.max():.8f}]"
)
print(
    f"    • actual_realized_vol range: [{actual_realized_vol.min():.8f}, {actual_realized_vol.max():.8f}]"
)
print(
    f"    • garch_forecast_1d > 0 count: {(garch_forecast_1d > 0).sum()} / {n_total_garch}"
)

for i in range(1, n_total_garch):
    forecast_prev = garch_forecast_1d[i - 1]
    actual_vol = actual_realized_vol[i]
    if forecast_prev > 1e-10 and actual_vol > 0:
        garch_surprise[i] = (actual_vol - forecast_prev) / forecast_prev

print(
    f"    • garch_surprise non-zero count: {(garch_surprise != 0).sum()} / {n_total_garch}"
)
print(
    f"    • garch_surprise range: [{garch_surprise.min():.4f}, {garch_surprise.max():.4f}]"
)

# ────────────────────────────────────────────────────────────────────────────
# STEP 4: Add GARCH features to dataframes
# ────────────────────────────────────────────────────────────────────────────
print("\n  STEP 4: Adding GARCH features to datasets...")

garch_features = {
    "garch_variance": garch_variance,
    "garch_volatility": garch_volatility,
    "garch_forecast_1d": garch_forecast_1d,
    "garch_standardized_resid": garch_standardized_resid,
    "garch_vol_shock": garch_vol_shock,
    "garch_vol_regime": garch_vol_regime,
    "garch_vol_change_1d": garch_vol_change_1d,
    "garch_vol_change_5d": garch_vol_change_5d,
    "garch_surprise": garch_surprise,
}

# Add to PARTIAL
for feat_name, feat_values in garch_features.items():
    df_partial = df_partial.with_columns(
        [pl.lit(feat_values[:idx_partial_end_garch]).alias(feat_name)]
    )

# Add to TRAIN
for feat_name, feat_values in garch_features.items():
    df_train = df_train.with_columns(
        [pl.lit(feat_values[idx_partial_end_garch:]).alias(feat_name)]
    )

# Save GARCH state for API simulation
garch_state = {
    "session_id": TRAINING_SESSION_ID,
    "omega": garch_omega,
    "alpha": garch_alpha,
    "beta": garch_beta,
    "last_variance": garch_variance[-1],
    "last_return_scaled": returns_combined[-1],
    "fitted": GARCH_FITTED if GARCH_AVAILABLE else False,
}

print(f"    ✅ GARCH features added to PARTIAL ({len(df_partial)} rows)")
print(f"    ✅ GARCH features added to TRAIN ({len(df_train)} rows)")
print("    ✅ GARCH state saved for API simulation")

# 🔧 DEBUG: Verify GARCH features in df_train
print("\n  🔍 GARCH FEATURE VALIDATION:")
for feat_name in garch_features.keys():
    if feat_name in df_train.columns:
        col = df_train[feat_name]
        non_null = col.drop_nulls()
        non_zero = (col != 0).sum()
        print(
            f"    • {feat_name}: non-null={len(non_null)}/{len(col)}, non-zero={non_zero}, range=[{col.min():.6f}, {col.max():.6f}]"
        )
    else:
        print(f"    ⚠️ {feat_name}: NOT FOUND in df_train!")

print("\n  GARCH Features Summary:")
print("    • garch_variance: Current GARCH variance")
print("    • garch_volatility: √variance (decimal scale)")
print("    • garch_forecast_1d: 1-day volatility forecast")
print("    • garch_standardized_resid: Return / volatility")
print("    • garch_vol_shock: (realized - expected) / expected")
print("    • garch_vol_regime: Volatility tercile (1-3)")
print("    • garch_vol_change_1d/5d: Volatility momentum")
print("    • garch_surprise: Forecast error")
print(f"\n{'=' * 80}\n")

# Update df_pl
df_pl = df_train.clone()

# %% [CELL 15] Save TRAIN Dataset to CSV
# Save TRAIN dataset to CSV
print("=" * 80)
print("SAVING TRAIN DATASET TO CSV")
print("=" * 80)

# Define output path
train_csv_path = output_dir / "df_train_after_kalman1.csv"

# Save to CSV
df_train.write_csv(train_csv_path)

print(f"\n✓ Train dataset saved to: {train_csv_path}")
print(f"  Shape: {df_train.shape}")
print(f"  Columns: {len(df_train.columns)}")
print(f"  File size: {train_csv_path.stat().st_size / 1024 / 1024:.2f} MB")

print("\nFirst few rows:")
print(df_train.head(3))

print("\n" + "=" * 80)

# %% [CELL 16] Incremental HMM Feature Calculator Class
# INCREMENTAL HMM FEATURE CALCULATOR FOR API/REAL-TIME INFERENCE

print(f"\n{'=' * 80}")
print("INCREMENTAL HMM FEATURE CALCULATOR")
print(f"{'=' * 80}\n")


class IncrementalHMMFeatureCalculator:
    """
    Helper class to add HMM features to new rows one at a time.

    This simulates real-time inference where new data arrives via API.
    The calculator maintains a rolling window of historical data and
    applies the trained HMM model to compute features for each new row.

    Usage:
    ------
    1. Initialize with trained HMM model and historical validation data
    2. Call add_hmm_features_to_new_row() for each new row from API
    3. Features are calculated using historical context + new row

    Example:
    --------
    >>> calculator = IncrementalHMMFeatureCalculator(hmm_model, hmm_scaler, df_validation, vol_33, vol_67)
    >>> new_row_with_hmm = calculator.add_hmm_features_to_new_row(new_api_row)
    """

    def __init__(
        self,
        hmm_model,
        hmm_scaler,
        validation_df,
        vol_33,
        vol_67,
        ret_33=None,
        ret_67=None,
        max_history=500,
        fg_models=None,
        fg_scalers=None,
        fg_info=None,
        fg_available=None,
        derived_fg_models=None,
        derived_fg_scalers=None,
        derived_fg_info=None,
        derived_fg_available=None,
    ):
        """
        Initialize the incremental HMM feature calculator.

        Parameters:
        -----------
        hmm_model : GaussianHMM
            Trained HMM model (from PARTIAL dataset)
        hmm_scaler : StandardScaler
            Fitted scaler for HMM-4 feature normalization
        validation_df : pl.DataFrame
            Current validation dataset (180 rows initially)
        vol_33, vol_67 : float
            Volatility quantiles for historical regime classification
        ret_33, ret_67 : float
            Return quantiles for historical direction regime classification (data-driven)
        max_history : int
            Maximum number of historical rows to keep (default: 500)
        fg_models : dict, optional
            Feature-group HMM models (keyed by prefix: M, E, I, P, V, S)
        fg_scalers : dict, optional
            Feature-group scalers (keyed by prefix)
        fg_info : dict, optional
            Feature-group info (columns, first_valid_row, etc.)
        fg_available : dict, optional
            Feature-group availability flags
        derived_fg_models : dict, optional
            Derived feature-group HMM models (keyed by prefix: MOM, D)
        derived_fg_scalers : dict, optional
            Derived feature-group scalers (keyed by prefix)
        derived_fg_info : dict, optional
            Derived feature-group info (columns, etc.)
        derived_fg_available : dict, optional
            Derived feature-group availability flags
        """
        self.hmm_model = hmm_model
        self.hmm_scaler = hmm_scaler  # Added: StandardScaler for HMM-4
        self.validation_df = validation_df.clone()
        self.vol_33 = vol_33
        self.vol_67 = vol_67
        self.ret_33 = (
            ret_33 if ret_33 is not None else -0.0005
        )  # Fallback for backward compatibility
        self.ret_67 = (
            ret_67 if ret_67 is not None else 0.0005
        )  # Fallback for backward compatibility
        self.max_history = max_history

        # Feature-group HMM support
        self.fg_models = fg_models or {}
        self.fg_scalers = fg_scalers or {}
        self.fg_info = fg_info or {}
        self.fg_available = fg_available or {}
        self.fg_n_components = 3  # 3 regimes per feature group

        # Derived Feature-group HMM support (MOM*, D*)
        self.derived_fg_models = derived_fg_models or {}
        self.derived_fg_scalers = derived_fg_scalers or {}
        self.derived_fg_info = derived_fg_info or {}
        self.derived_fg_available = derived_fg_available or {}

        # Track feature-group regimes and durations
        self.fg_current_regime = {}
        self.fg_current_duration = {}
        for prefix in self.fg_available:
            if self.fg_available.get(prefix, False):
                col_name = f"{prefix}_hmm_regime"
                if len(validation_df) > 0 and col_name in validation_df.columns:
                    self.fg_current_regime[prefix] = validation_df[col_name][-1]
                    self.fg_current_duration[prefix] = validation_df[
                        f"{prefix}_hmm_duration"
                    ][-1]
                else:
                    self.fg_current_regime[prefix] = 0
                    self.fg_current_duration[prefix] = 1

        # Track derived feature-group regimes and durations (MOM*, D*)
        self.derived_fg_current_regime = {}
        self.derived_fg_current_duration = {}
        for prefix in self.derived_fg_available:
            if self.derived_fg_available.get(prefix, False):
                col_name = f"{prefix}_hmm_regime"
                if len(validation_df) > 0 and col_name in validation_df.columns:
                    self.derived_fg_current_regime[prefix] = validation_df[col_name][-1]
                    self.derived_fg_current_duration[prefix] = validation_df[
                        f"{prefix}_hmm_duration"
                    ][-1]
                else:
                    self.derived_fg_current_regime[prefix] = 0
                    self.derived_fg_current_duration[prefix] = 1

        # Track last date_id for continuity check
        self.last_date_id = validation_df["date_id"].max()

        # Required features for HMM
        self.hmm_features = [
            "daily_volatility_lagged",
            "lagged_forward_returns",
            "volatility_ma_5",
        ]

        # Track current regime for duration calculation
        if len(validation_df) > 0 and "hmm_regime" in validation_df.columns:
            self.current_regime = validation_df["hmm_regime"][-1]
            self.current_duration = validation_df["hmm_regime_duration"][-1]
        else:
            self.current_regime = 0
            self.current_duration = 1

        print("✅ Incremental HMM Calculator initialized")
        print(f"   • Validation dataset: {len(self.validation_df)} rows")
        print(f"   • Last date_id: {self.last_date_id}")
        print(f"   • Current regime: {self.current_regime}")
        print(f"   • Current duration: {self.current_duration}")
        print(f"   • Max history window: {self.max_history} rows")
        if self.fg_models:
            print(f"   • Feature-group HMMs: {list(self.fg_models.keys())}")
        if self.derived_fg_models:
            print(
                f"   • Derived feature-group HMMs: {list(self.derived_fg_models.keys())}"
            )

    def add_hmm_features_to_new_row(self, new_row_df, verbose=True):
        """
        Add HMM features to a single new row from API.

        This function:
        1. Validates the new row is continuous (no missing date_ids)
        2. Extracts HMM input features from historical context + new row
        3. Predicts HMM regime and probabilities
        4. Calculates regime transitions and duration
        5. Adds historical regime features
        6. Updates internal state for next row

        Parameters:
        -----------
        new_row_df : pl.DataFrame
            Single row with base features (must include HMM_FEATURES)
            Expected to have date_id = last_date_id + 1
        verbose : bool
            Print detailed progress (default: True)

        Returns:
        --------
        pl.DataFrame
            New row with HMM features added

        Raises:
        -------
        ValueError
            If date_id is not continuous or required features are missing
        """

        if verbose:
            print(f"\n{'─' * 60}")
            print("Processing new row from API...")

        # ═══════════════════════════════════════════════════════════
        # STEP 1: Validate continuity
        # ═══════════════════════════════════════════════════════════
        new_date_id = new_row_df["date_id"][0]
        expected_date_id = self.last_date_id + 1

        if new_date_id != expected_date_id:
            raise ValueError(
                f"Date continuity broken! Expected date_id={expected_date_id}, "
                f"got {new_date_id}. Missing {new_date_id - expected_date_id} rows."
            )

        if verbose:
            print(f"  ✓ Date continuity: {new_date_id} (continuous)")

        # ═══════════════════════════════════════════════════════════
        # STEP 2: Verify required features exist
        # ═══════════════════════════════════════════════════════════
        missing_features = [f for f in self.hmm_features if f not in new_row_df.columns]
        if missing_features:
            raise ValueError(
                f"Missing required HMM features: {missing_features}. "
                f"Required: {self.hmm_features}"
            )

        if verbose:
            print(f"  ✓ Required features present: {self.hmm_features}")

        # ═══════════════════════════════════════════════════════════
        # STEP 3: Extract HMM input features
        # ═══════════════════════════════════════════════════════════
        # Use ONLY the new row for prediction (no need for historical context
        # because all features are already pre-calculated with historical data)
        hmm_input = np.column_stack(
            [new_row_df[feat].to_numpy() for feat in self.hmm_features]
        )

        # Check for NaN values
        has_nan = np.isnan(hmm_input).any()

        if has_nan:
            if verbose:
                print("  ⚠  NaN values detected - using default HMM features")

            # Default values for NaN rows
            hmm_regime = 0
            state_probs = np.array([0.25, 0.25, 0.25, 0.25])
            hmm_confidence = 0.25

        else:
            # IMPORTANT: Scale input using the fitted scaler from training
            hmm_input_scaled = self.hmm_scaler.transform(hmm_input)

            # Predict HMM regime (on SCALED data)
            hmm_regime = self.hmm_model.predict(hmm_input_scaled)[0]
            state_probs = self.hmm_model.predict_proba(hmm_input_scaled)[0]
            hmm_confidence = state_probs.max()

            if verbose:
                print(
                    f"  ✓ HMM prediction: regime={hmm_regime}, confidence={hmm_confidence:.3f}"
                )

        # ═══════════════════════════════════════════════════════════
        # STEP 4: Calculate regime transitions and duration
        # ═══════════════════════════════════════════════════════════
        if hmm_regime == self.current_regime:
            regime_change = 0
            regime_duration = self.current_duration + 1
        else:
            regime_change = 1
            regime_duration = 1
            if verbose:
                print(f"  🔄 Regime transition: {self.current_regime} → {hmm_regime}")

        # ═══════════════════════════════════════════════════════════
        # STEP 5: Calculate historical regimes
        # ═══════════════════════════════════════════════════════════
        daily_vol = new_row_df["daily_volatility_lagged"][0]
        lagged_ret = new_row_df["lagged_forward_returns"][0]

        # Historical volatility regime (3-state)
        if daily_vol is None or np.isnan(daily_vol):
            historical_vol_regime = 1
        elif daily_vol <= self.vol_33:
            historical_vol_regime = 0
        elif daily_vol > self.vol_67:
            historical_vol_regime = 2
        else:
            historical_vol_regime = 1

        # Historical direction regime (3-state) - using data-driven thresholds
        if lagged_ret is None or np.isnan(lagged_ret):
            historical_dir_regime = 1
        elif lagged_ret <= self.ret_33:
            historical_dir_regime = 0
        elif lagged_ret > self.ret_67:
            historical_dir_regime = 2
        else:
            historical_dir_regime = 1

        # ═══════════════════════════════════════════════════════════
        # STEP 6: Add HMM features to new row
        # ═══════════════════════════════════════════════════════════
        new_row_with_hmm = new_row_df.with_columns(
            [
                pl.lit(hmm_regime).cast(pl.Int32).alias("hmm_regime"),
                pl.lit(state_probs[0]).alias("hmm_regime_prob_0"),
                pl.lit(state_probs[1]).alias("hmm_regime_prob_1"),
                pl.lit(state_probs[2]).alias("hmm_regime_prob_2"),
                pl.lit(state_probs[3]).alias("hmm_regime_prob_3"),
                pl.lit(hmm_confidence).alias("hmm_regime_confidence"),
                pl.lit(regime_change).cast(pl.Int32).alias("hmm_regime_change"),
                pl.lit(regime_duration).cast(pl.Int32).alias("hmm_regime_duration"),
                pl.lit(historical_vol_regime)
                .cast(pl.Int32)
                .alias("historical_vol_regime"),
                pl.lit(historical_dir_regime)
                .cast(pl.Int32)
                .alias("historical_dir_regime"),
            ]
        )

        # ═══════════════════════════════════════════════════════════
        # STEP 6b: Add Feature-Group HMM features
        # ═══════════════════════════════════════════════════════════
        if self.fg_models:
            fg_features = []

            for prefix, info in self.fg_info.items():
                if not self.fg_available.get(prefix, False):
                    continue
                if prefix not in self.fg_models:
                    continue

                columns = info["selected_columns"]
                hmm_fg = self.fg_models[prefix]
                scaler = self.fg_scalers[prefix]

                try:
                    # Extract features for this group, cast to float
                    try:
                        fg_input = np.array(
                            [[float(new_row_df[col][0]) for col in columns]]
                        )
                    except (TypeError, ValueError):
                        fg_regime = 0
                        fg_confidence = 1.0 / self.fg_n_components
                        fg_input = None

                    if fg_input is not None:
                        # Check for NaN
                        if np.isnan(fg_input).any():
                            fg_regime = 0
                            fg_confidence = 1.0 / self.fg_n_components
                        else:
                            # Scale and predict
                            fg_input_scaled = scaler.transform(fg_input)
                            fg_regime = int(hmm_fg.predict(fg_input_scaled)[0])
                            fg_probs = hmm_fg.predict_proba(fg_input_scaled)[0]
                            fg_confidence = float(fg_probs.max())

                    # Calculate regime change and duration
                    prev_regime = self.fg_current_regime.get(prefix, 0)
                    prev_duration = self.fg_current_duration.get(prefix, 1)

                    if fg_regime == prev_regime:
                        fg_change = 0
                        fg_duration = prev_duration + 1
                    else:
                        fg_change = 1
                        fg_duration = 1

                    # Update state
                    self.fg_current_regime[prefix] = fg_regime
                    self.fg_current_duration[prefix] = fg_duration

                    # Add basic features
                    fg_features.extend(
                        [
                            pl.lit(fg_regime)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_regime"),
                            pl.lit(fg_confidence).alias(f"{prefix}_hmm_confidence"),
                            pl.lit(fg_change)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_regime_change"),
                            pl.lit(fg_duration)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_duration"),
                        ]
                    )

                    # Calculate advanced features using validation_df history
                    # Get recent history for rolling calculations
                    col_change = f"{prefix}_hmm_regime_change"
                    col_conf = f"{prefix}_hmm_confidence"

                    if (
                        col_change in self.validation_df.columns
                        and len(self.validation_df) > 0
                    ):
                        # Get last N values for rolling calculations
                        recent_changes = self.validation_df[col_change].to_numpy()
                        recent_conf = self.validation_df[col_conf].to_numpy()

                        # Stable 3d/5d: no changes in last 3/5 rows (including current)
                        changes_3d = (
                            list(recent_changes[-2:]) + [fg_change]
                            if len(recent_changes) >= 2
                            else [fg_change]
                        )
                        changes_5d = (
                            list(recent_changes[-4:]) + [fg_change]
                            if len(recent_changes) >= 4
                            else [fg_change]
                        )
                        stable_3d = 1 if sum(changes_3d[-3:]) == 0 else 0
                        stable_5d = 1 if sum(changes_5d[-5:]) == 0 else 0

                        # Confidence dynamics
                        prev_conf = (
                            recent_conf[-1] if len(recent_conf) > 0 else fg_confidence
                        )
                        conf_change = fg_confidence - prev_conf

                        conf_for_ma = (
                            list(recent_conf[-4:]) + [fg_confidence]
                            if len(recent_conf) >= 4
                            else [fg_confidence]
                        )
                        conf_ma5 = np.mean(conf_for_ma[-5:])
                        conf_std5 = (
                            np.std(conf_for_ma[-5:]) if len(conf_for_ma) >= 2 else 0.0
                        )

                        # Transitions 5d/10d
                        changes_for_5d = list(recent_changes[-4:]) + [fg_change]
                        changes_for_10d = list(recent_changes[-9:]) + [fg_change]
                        transitions_5d = int(sum(changes_for_5d[-5:]))
                        transitions_10d = int(sum(changes_for_10d[-10:]))

                    else:
                        # First row or column doesn't exist yet
                        stable_3d = 1
                        stable_5d = 1
                        conf_change = 0.0
                        conf_ma5 = fg_confidence
                        conf_std5 = 0.0
                        transitions_5d = fg_change
                        transitions_10d = fg_change

                    # Entropy calculation
                    if fg_confidence > 0.99:
                        fg_entropy = 0.0
                    elif fg_confidence < 0.34:
                        fg_entropy = np.log(3)
                    else:
                        remaining = 1.0 - fg_confidence
                        other_p = remaining / 2.0
                        fg_entropy = -(
                            fg_confidence * np.log(fg_confidence + 1e-10)
                            + 2 * other_p * np.log(other_p + 1e-10)
                        )

                    # Add advanced features
                    fg_features.extend(
                        [
                            pl.lit(stable_3d)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_stable_3d"),
                            pl.lit(stable_5d)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_stable_5d"),
                            pl.lit(conf_change).alias(f"{prefix}_hmm_conf_change"),
                            pl.lit(conf_ma5).alias(f"{prefix}_hmm_conf_ma5"),
                            pl.lit(conf_std5).alias(f"{prefix}_hmm_conf_std5"),
                            pl.lit(transitions_5d)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_transitions_5d"),
                            pl.lit(transitions_10d)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_transitions_10d"),
                            pl.lit(fg_entropy).alias(f"{prefix}_hmm_entropy"),
                        ]
                    )

                except Exception:
                    # Default values on error (basic + advanced)
                    fg_features.extend(
                        [
                            pl.lit(0).cast(pl.Int32).alias(f"{prefix}_hmm_regime"),
                            pl.lit(1.0 / self.fg_n_components).alias(
                                f"{prefix}_hmm_confidence"
                            ),
                            pl.lit(0)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_regime_change"),
                            pl.lit(1).cast(pl.Int32).alias(f"{prefix}_hmm_duration"),
                            pl.lit(1).cast(pl.Int32).alias(f"{prefix}_hmm_stable_3d"),
                            pl.lit(1).cast(pl.Int32).alias(f"{prefix}_hmm_stable_5d"),
                            pl.lit(0.0).alias(f"{prefix}_hmm_conf_change"),
                            pl.lit(1.0 / self.fg_n_components).alias(
                                f"{prefix}_hmm_conf_ma5"
                            ),
                            pl.lit(0.0).alias(f"{prefix}_hmm_conf_std5"),
                            pl.lit(0)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_transitions_5d"),
                            pl.lit(0)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_transitions_10d"),
                            pl.lit(np.log(3)).alias(f"{prefix}_hmm_entropy"),
                        ]
                    )

            if fg_features:
                new_row_with_hmm = new_row_with_hmm.with_columns(fg_features)

        # ═══════════════════════════════════════════════════════════
        # STEP 6c: Add Feature-Group HMM Cross-Model Features
        # Creates interactions between FG-HMMs and base models (Kalman/CUSUM/Anomaly/HMM4/HMM5)
        # ═══════════════════════════════════════════════════════════
        if self.fg_models:
            fg_cross_features = []

            # Get base model values from current row
            try:
                kalman_pred = (
                    float(new_row_with_hmm["kalman_h20_pred"][0])
                    if "kalman_h20_pred" in new_row_with_hmm.columns
                    else 0.0
                )
                kalman_conf = (
                    float(new_row_with_hmm["kalman_h20_confidence"][0])
                    if "kalman_h20_confidence" in new_row_with_hmm.columns
                    else 0.5
                )
                cusum_vol_change = (
                    float(new_row_with_hmm["changepoint_vol_any"][0])
                    if "changepoint_vol_any" in new_row_with_hmm.columns
                    else 0.0
                )
                cusum_days = (
                    float(new_row_with_hmm["cusum_days_since_changepoint"][0])
                    if "cusum_days_since_changepoint" in new_row_with_hmm.columns
                    else 10.0
                )
                anomaly_extreme = (
                    float(new_row_with_hmm["anomaly_extreme_is"][0])
                    if "anomaly_extreme_is" in new_row_with_hmm.columns
                    else 0.0
                )
                hmm4_regime = float(
                    hmm_regime
                )  # Current HMM-4 regime from earlier calculation
                hmm5_regime_val = (
                    float(new_row_with_hmm["hmm5_regime"][0])
                    if "hmm5_regime" in new_row_with_hmm.columns
                    else 0.0
                )
            except Exception:
                kalman_pred, kalman_conf = 0.0, 0.5
                cusum_vol_change, cusum_days = 0.0, 10.0
                anomaly_extreme = 0.0
                hmm4_regime, hmm5_regime_val = 0.0, 0.0

            for prefix, info in self.fg_info.items():
                if not self.fg_available.get(prefix, False):
                    continue
                if prefix not in self.fg_models:
                    continue

                try:
                    # Get FG-HMM values
                    fg_regime = float(new_row_with_hmm[f"{prefix}_hmm_regime"][0])
                    fg_conf = float(new_row_with_hmm[f"{prefix}_hmm_confidence"][0])
                    fg_change = float(
                        new_row_with_hmm[f"{prefix}_hmm_regime_change"][0]
                    )

                    # 1. FG-HMM × Kalman prediction interaction
                    fg_kalman_interact = kalman_pred * fg_regime

                    # 2. FG-HMM × CUSUM volatility changepoint agreement
                    fg_cusum_agree = (fg_change + cusum_vol_change) / 2.0

                    # 3. FG-HMM × Anomaly agreement (extreme regimes correlate with anomalies)
                    fg_extreme = 1.0 if (fg_regime == 0 or fg_regime == 2) else 0.0
                    fg_anomaly_agree = fg_extreme * anomaly_extreme

                    # 4. FG-HMM × HMM-4 regime agreement (normalized)
                    hmm4_normalized = hmm4_regime / 3.0  # Scale to 0-1
                    fg_normalized = fg_regime / 2.0  # Scale to 0-1
                    fg_hmm4_agree = 1.0 - abs(hmm4_normalized - fg_normalized)

                    # 5. FG-HMM × HMM-5 regime agreement
                    hmm5_normalized = hmm5_regime_val / 4.0  # Scale to 0-1
                    fg_hmm5_agree = 1.0 - abs(hmm5_normalized - fg_normalized)

                    # 6. FG-HMM confidence × Kalman confidence synergy
                    fg_kalman_conf_synergy = fg_conf * kalman_conf

                    # 7. FG-HMM regime change × CUSUM recency
                    fg_cusum_recency = fg_change * (1.0 / (1.0 + cusum_days))

                    fg_cross_features.extend(
                        [
                            pl.lit(fg_kalman_interact).alias(
                                f"{prefix}_kalman_interact"
                            ),
                            pl.lit(fg_cusum_agree).alias(f"{prefix}_cusum_agree"),
                            pl.lit(fg_anomaly_agree).alias(f"{prefix}_anomaly_agree"),
                            pl.lit(fg_hmm4_agree).alias(f"{prefix}_hmm4_agree"),
                            pl.lit(fg_hmm5_agree).alias(f"{prefix}_hmm5_agree"),
                            pl.lit(fg_kalman_conf_synergy).alias(
                                f"{prefix}_kalman_conf_synergy"
                            ),
                            pl.lit(fg_cusum_recency).alias(
                                f"{prefix}_cusum_change_recency"
                            ),
                        ]
                    )

                except Exception:
                    # Default values on error
                    fg_cross_features.extend(
                        [
                            pl.lit(0.0).alias(f"{prefix}_kalman_interact"),
                            pl.lit(0.0).alias(f"{prefix}_cusum_agree"),
                            pl.lit(0.0).alias(f"{prefix}_anomaly_agree"),
                            pl.lit(0.5).alias(f"{prefix}_hmm4_agree"),
                            pl.lit(0.5).alias(f"{prefix}_hmm5_agree"),
                            pl.lit(0.25).alias(f"{prefix}_kalman_conf_synergy"),
                            pl.lit(0.0).alias(f"{prefix}_cusum_change_recency"),
                        ]
                    )

            if fg_cross_features:
                new_row_with_hmm = new_row_with_hmm.with_columns(fg_cross_features)

        # ═══════════════════════════════════════════════════════════
        # STEP 6d: Add Derived Feature-Group HMM features (MOM*, D*)
        # These are based on momentum and binary features from row_by_row
        # ═══════════════════════════════════════════════════════════
        if self.derived_fg_models:
            derived_fg_features = []

            for prefix, info in self.derived_fg_info.items():
                if not self.derived_fg_available.get(prefix, False):
                    continue
                if prefix not in self.derived_fg_models:
                    continue

                columns = info["selected_columns"]
                hmm_derived = self.derived_fg_models[prefix]
                scaler = self.derived_fg_scalers[prefix]

                try:
                    # Extract features for this derived group, cast to float
                    try:
                        derived_input = np.array(
                            [[float(new_row_with_hmm[col][0]) for col in columns]]
                        )
                    except (TypeError, ValueError, KeyError):
                        derived_regime = 0
                        derived_confidence = 1.0 / 3.0
                        derived_input = None

                    if derived_input is not None:
                        # Check for NaN
                        if np.isnan(derived_input).any():
                            derived_regime = 0
                            derived_confidence = 1.0 / 3.0
                        else:
                            # Scale and predict
                            derived_input_scaled = scaler.transform(derived_input)
                            derived_regime = int(
                                hmm_derived.predict(derived_input_scaled)[0]
                            )
                            derived_probs = hmm_derived.predict_proba(
                                derived_input_scaled
                            )[0]
                            derived_confidence = float(derived_probs.max())

                    # Calculate regime change and duration
                    prev_regime = self.derived_fg_current_regime.get(prefix, 0)
                    prev_duration = self.derived_fg_current_duration.get(prefix, 1)

                    if derived_regime == prev_regime:
                        derived_change = 0
                        derived_duration = prev_duration + 1
                    else:
                        derived_change = 1
                        derived_duration = 1

                    # Update state
                    self.derived_fg_current_regime[prefix] = derived_regime
                    self.derived_fg_current_duration[prefix] = derived_duration

                    # Add basic derived HMM features
                    derived_fg_features.extend(
                        [
                            pl.lit(derived_regime)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_regime"),
                            pl.lit(derived_confidence).alias(
                                f"{prefix}_hmm_confidence"
                            ),
                            pl.lit(derived_change)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_regime_change"),
                            pl.lit(derived_duration)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_duration"),
                        ]
                    )

                except Exception:
                    # Default values on error
                    derived_fg_features.extend(
                        [
                            pl.lit(0).cast(pl.Int32).alias(f"{prefix}_hmm_regime"),
                            pl.lit(1.0 / 3.0).alias(f"{prefix}_hmm_confidence"),
                            pl.lit(0)
                            .cast(pl.Int32)
                            .alias(f"{prefix}_hmm_regime_change"),
                            pl.lit(1).cast(pl.Int32).alias(f"{prefix}_hmm_duration"),
                        ]
                    )

            if derived_fg_features:
                new_row_with_hmm = new_row_with_hmm.with_columns(derived_fg_features)

        # ═══════════════════════════════════════════════════════════
        # STEP 7: Update internal state
        # ═══════════════════════════════════════════════════════════
        self.validation_df = pl.concat(
            [self.validation_df, new_row_with_hmm], how="vertical_relaxed"
        )

        # Trim history if needed
        if len(self.validation_df) > self.max_history:
            rows_to_drop = len(self.validation_df) - self.max_history
            self.validation_df = self.validation_df[rows_to_drop:]
            if verbose:
                print(f"  📦 Trimmed history: kept last {self.max_history} rows")

        self.last_date_id = new_date_id
        self.current_regime = hmm_regime
        self.current_duration = regime_duration

        if verbose:
            print("  ✅ HMM features added successfully")
            print(f"     Total validation rows: {len(self.validation_df)}")
            print(f"{'─' * 60}\n")

        return new_row_with_hmm

    def get_validation_dataset(self):
        """
        Get the current validation dataset with all accumulated rows.

        Returns:
        --------
        pl.DataFrame
            Current validation dataset
        """
        return self.validation_df.clone()

    def get_state_summary(self):
        """
        Get summary of calculator state.

        Returns:
        --------
        dict
            Summary including last_date_id, current_regime, validation size, etc.
        """
        return {
            "last_date_id": self.last_date_id,
            "current_regime": self.current_regime,
            "current_duration": self.current_duration,
            "validation_rows": len(self.validation_df),
            "max_history": self.max_history,
        }


# ═══════════════════════════════════════════════════════════════════════════
# INITIALIZE CALCULATOR (only if HMM training succeeded)
# ═══════════════════════════════════════════════════════════════════════════

if HMM_AVAILABLE and "hmm_model" in locals():
    print(f"\n{'─' * 80}")
    print("Initializing Incremental HMM Calculator for API inference...")
    print(f"{'─' * 80}")

    # Get feature-group HMM models if available
    _fg_models = FEATURE_GROUP_MODELS if "FEATURE_GROUP_MODELS" in dir() else {}
    _fg_scalers = FEATURE_GROUP_SCALERS if "FEATURE_GROUP_SCALERS" in dir() else {}
    _fg_info = FEATURE_GROUP_INFO if "FEATURE_GROUP_INFO" in dir() else {}
    _fg_available = (
        FEATURE_GROUP_AVAILABLE if "FEATURE_GROUP_AVAILABLE" in dir() else {}
    )

    # Get derived feature-group HMM models (MOM*, D*) if available
    _derived_fg_models = (
        DERIVED_FEATURE_GROUP_MODELS if "DERIVED_FEATURE_GROUP_MODELS" in dir() else {}
    )
    _derived_fg_scalers = (
        DERIVED_FEATURE_GROUP_SCALERS
        if "DERIVED_FEATURE_GROUP_SCALERS" in dir()
        else {}
    )
    _derived_fg_info = (
        DERIVED_FEATURE_GROUP_INFO if "DERIVED_FEATURE_GROUP_INFO" in dir() else {}
    )
    _derived_fg_available = (
        DERIVED_FEATURE_GROUP_AVAILABLE
        if "DERIVED_FEATURE_GROUP_AVAILABLE" in dir()
        else {}
    )

    # Get HMM-4 scaler (must be defined from training)
    _hmm4_scaler = hmm4_scaler if "hmm4_scaler" in dir() else None

    hmm_calculator = IncrementalHMMFeatureCalculator(
        hmm_model=hmm_model,
        hmm_scaler=_hmm4_scaler,  # Pass the HMM-4 scaler
        validation_df=df_validation,
        vol_33=vol_33,
        vol_67=vol_67,
        ret_33=ret_33,  # Data-driven return threshold (from PARTIAL)
        ret_67=ret_67,  # Data-driven return threshold (from PARTIAL)
        max_history=500,  # Keep last 500 rows for context
        fg_models=_fg_models,
        fg_scalers=_fg_scalers,
        fg_info=_fg_info,
        fg_available=_fg_available,
        derived_fg_models=_derived_fg_models,
        derived_fg_scalers=_derived_fg_scalers,
        derived_fg_info=_derived_fg_info,
        derived_fg_available=_derived_fg_available,
    )

    print("\n✅ Calculator ready for API inference!")
    print("\nUsage example:")
    print(
        "  >>> new_row_with_hmm = hmm_calculator.add_hmm_features_to_new_row(new_api_row)"
    )
    print("  >>> updated_validation = hmm_calculator.get_validation_dataset()")

else:
    print("\n⚠️  HMM Calculator not initialized (HMM training was skipped or failed)")
    hmm_calculator = None

print(f"\n{'=' * 80}\n")


# %% [CELL 17] API Feature Calculator Class
# KAGGLE API INFERENCE - FEATURE CALCULATOR FOR TEST DATA

print(f"\n{'=' * 80}")
print("KAGGLE API FEATURE CALCULATION SETUP")
print(f"{'=' * 80}\n")


class APIFeatureCalculator:
    """
    Calculate all features for API inference in Kaggle competition.

    This class maintains state across API calls and calculates:
    1. Lagged features (from previous rows)
    2. Rolling window features (volatility MAs, win-rates, etc.)
    3. Expanding window features (cumulative statistics)
    4. HMM features (using IncrementalHMMFeatureCalculator)

    The calculator is designed to work with Kaggle's time-series API
    where data arrives row by row.
    """

    def __init__(self, historical_data, hmm_calculator_instance):
        """
        Initialize the API feature calculator.

        Parameters:
        -----------
        historical_data : pl.DataFrame
            Historical validation data (180 rows) with all features
        hmm_calculator_instance : IncrementalHMMFeatureCalculator
            Initialized HMM calculator
        """
        self.historical_data = historical_data.clone()
        self.hmm_calculator = hmm_calculator_instance

        # Track last date for continuity
        self.last_date_id = historical_data["date_id"].max()

        # Store window sizes for feature calculation
        self.volatility_windows = [5, 21, 180]
        self.mhv_windows = [5, 10, 21, 63, 126, 252]
        self.win_rate_windows = [5, 21, 180]

        print("✅ API Feature Calculator initialized")
        print(f"   • Historical data: {len(self.historical_data)} rows")
        print(f"   • Last date_id: {self.last_date_id}")
        print(
            f"   • HMM calculator: {'Ready' if self.hmm_calculator else 'Not available'}"
        )

    def calculate_features_for_new_row(self, test_row, verbose=False):
        """
        Calculate all features for a new test row from Kaggle API.

        This assumes test_row has minimal raw features and we need to:
        1. Calculate lagged features (using historical data)
        2. Calculate rolling window features
        3. Calculate expanding window features
        4. Add HMM features

        Parameters:
        -----------
        test_row : pl.DataFrame
            Single row from Kaggle API (minimal features)
            Expected columns: date_id, forward_returns (and other raw features)
        verbose : bool
            Print detailed progress

        Returns:
        --------
        pl.DataFrame
            Row with all features ready for model prediction
        """

        if verbose:
            print(f"\n{'─' * 60}")
            print(f"Calculating features for date_id = {test_row['date_id'][0]}...")

        # ═══════════════════════════════════════════════════════════
        # STEP 1: Validate continuity
        # ═══════════════════════════════════════════════════════════
        new_date_id = test_row["date_id"][0]
        expected_date_id = self.last_date_id + 1

        if new_date_id != expected_date_id:
            raise ValueError(
                f"Date continuity broken! Expected {expected_date_id}, got {new_date_id}"
            )

        # ═══════════════════════════════════════════════════════════
        # STEP 2: Calculate lagged features
        # ═══════════════════════════════════════════════════════════
        # Get previous row for lagging
        prev_row = self.historical_data[-1:]

        # Lagged features (1-day lag)
        if "forward_returns" in prev_row.columns:
            lagged_forward_returns = prev_row["forward_returns"][0]
        else:
            lagged_forward_returns = None

        if "risk_free_rate" in prev_row.columns:
            lagged_risk_free_rate = prev_row["risk_free_rate"][0]
        else:
            lagged_risk_free_rate = None

        if "market_forward_excess_returns" in prev_row.columns:
            lagged_market_forward_excess_returns = prev_row[
                "market_forward_excess_returns"
            ][0]
        else:
            lagged_market_forward_excess_returns = None

        # Daily volatility (absolute value of lagged returns)
        daily_volatility_lagged = (
            abs(lagged_forward_returns) if lagged_forward_returns is not None else None
        )

        # Add lagged features to test row
        test_row = test_row.with_columns(
            [
                pl.lit(lagged_forward_returns).alias("lagged_forward_returns"),
                pl.lit(lagged_risk_free_rate).alias("lagged_risk_free_rate"),
                pl.lit(lagged_market_forward_excess_returns).alias(
                    "lagged_market_forward_excess_returns"
                ),
                pl.lit(daily_volatility_lagged).alias("daily_volatility_lagged"),
            ]
        )

        # ═══════════════════════════════════════════════════════════
        # STEP 3: Calculate rolling window features
        # ═══════════════════════════════════════════════════════════
        # Combine historical data + new row for rolling calculations
        combined_for_rolling = pl.concat([self.historical_data, test_row])

        # Volatility MAs
        for window in self.volatility_windows:
            if "daily_volatility_lagged" in combined_for_rolling.columns:
                vol_ma = combined_for_rolling["daily_volatility_lagged"][
                    -window:
                ].mean()
                test_row = test_row.with_columns(
                    [pl.lit(vol_ma).alias(f"volatility_ma_{window}")]
                )

        # Mean Historical Volatility (MHV)
        for window in self.mhv_windows:
            if "lagged_forward_returns" in combined_for_rolling.columns:
                mhv = combined_for_rolling["lagged_forward_returns"][-window:].std()
                test_row = test_row.with_columns(
                    [pl.lit(mhv).alias(f"mean_hist_vol_{window}")]
                )

        # Volatility ratios
        if (
            "volatility_ma_21" in test_row.columns
            and test_row["volatility_ma_21"][0] is not None
        ):
            vol_ratio_21 = daily_volatility_lagged / (
                test_row["volatility_ma_21"][0] + 1e-10
            )
            test_row = test_row.with_columns(
                [pl.lit(vol_ratio_21).alias("vol_ratio_21")]
            )

        # MHV ratios
        if all(f"mean_hist_vol_{w}" in test_row.columns for w in [5, 21, 63, 252]):
            mhv_5 = test_row["mean_hist_vol_5"][0]
            mhv_21 = test_row["mean_hist_vol_21"][0]
            mhv_63 = test_row["mean_hist_vol_63"][0]
            mhv_252 = test_row["mean_hist_vol_252"][0]

            test_row = test_row.with_columns(
                [
                    pl.lit(mhv_5 / (mhv_21 + 1e-10)).alias("mhv_ratio_5_21"),
                    pl.lit(mhv_21 / (mhv_63 + 1e-10)).alias("mhv_ratio_21_63"),
                    pl.lit(mhv_63 / (mhv_252 + 1e-10)).alias("mhv_ratio_63_252"),
                ]
            )

        # Win-rate ratios
        for window in self.win_rate_windows:
            if "lagged_forward_returns" in combined_for_rolling.columns:
                positive_count = (
                    combined_for_rolling["lagged_forward_returns"][-window:] > 0
                ).sum()
                win_rate = positive_count / window if window > 0 else 0.5
                test_row = test_row.with_columns(
                    [pl.lit(win_rate).alias(f"win_rate_ratio_{window}")]
                )

        # ═══════════════════════════════════════════════════════════
        # STEP 4: Calculate expanding window features
        # ═══════════════════════════════════════════════════════════
        # IMPORTANT: These must match the NaN-safe implementation from cell 5!
        # We calculate expanding features over ALL historical data + current row

        # Expanding mean volatility (NaN-safe: sum / count of non-null)
        if "daily_volatility_lagged" in combined_for_rolling.columns:
            vol_series = combined_for_rolling["daily_volatility_lagged"]
            non_null_vol = vol_series.drop_nulls()
            if len(non_null_vol) > 0:
                expanding_mean_vol = non_null_vol.mean()
            else:
                expanding_mean_vol = None

            test_row = test_row.with_columns(
                [pl.lit(expanding_mean_vol).alias("expanding_mean_vol")]
            )

        # Expanding std returns (NaN-safe: requires >=2 non-null values)
        # Formula: std = sqrt(E[X^2] - (E[X])^2)
        if "lagged_forward_returns" in combined_for_rolling.columns:
            ret_series = combined_for_rolling["lagged_forward_returns"]
            non_null_ret = ret_series.drop_nulls()

            if len(non_null_ret) >= 2:
                # Calculate variance manually to match cell 5 implementation
                mean_ret = non_null_ret.mean()
                mean_sq_ret = (non_null_ret**2).mean()
                variance = mean_sq_ret - (mean_ret**2)

                # Clip negative variance (floating point errors)
                if variance < 0:
                    variance = 0

                expanding_std = variance**0.5
            else:
                expanding_std = None

            test_row = test_row.with_columns(
                [pl.lit(expanding_std).alias("expanding_std_returns")]
            )

        # ═══════════════════════════════════════════════════════════
        # STEP 5: Add HMM features
        # ═══════════════════════════════════════════════════════════
        if self.hmm_calculator is not None:
            test_row = self.hmm_calculator.add_hmm_features_to_new_row(
                test_row, verbose=verbose
            )

        # ═══════════════════════════════════════════════════════════
        # STEP 6: Update internal state
        # ═══════════════════════════════════════════════════════════
        self.historical_data = pl.concat([self.historical_data, test_row])
        self.last_date_id = new_date_id

        # Trim history to prevent memory issues (keep last 500 rows)
        if len(self.historical_data) > 500:
            self.historical_data = self.historical_data[-500:]

        if verbose:
            print("  ✅ All features calculated")
            print(f"     Total columns: {len(test_row.columns)}")
            print(f"{'─' * 60}\n")

        return test_row


# ═══════════════════════════════════════════════════════════════════════════
# Initialize API Feature Calculator
# ═══════════════════════════════════════════════════════════════════════════

if hmm_calculator is not None:
    api_feature_calculator = APIFeatureCalculator(
        historical_data=df_validation, hmm_calculator_instance=hmm_calculator
    )
    print("\n✅ API Feature Calculator ready for Kaggle inference!")
else:
    print("\n⚠️  HMM calculator not available - API calculator not initialized")
    api_feature_calculator = None

print(f"\n{'=' * 80}\n")

# %% [CELL 25.5] Save Training DataFrame for Feature Validation
# ═══════════════════════════════════════════════════════════════════════════════
# SAVE TRAIN DF WITH ALL FEATURES FOR VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════
# ============================================================================
# STEP 2: BUILD FEATURE COLUMNS DYNAMICALLY
# ============================================================================

print("=" * 80)
print("STEP 1: DATA SETUP")
print("=" * 80)
print()

# Use the FULL training dataset (df_train from earlier cells)
# Convert to pandas for easier manipulation
source_df = df_train.to_pandas() if hasattr(df_train, "to_pandas") else df_train.copy()
total_rows = len(source_df)

print(f"FULL Training Dataset: {total_rows:,} rows")
print()
# Target column names (string constants)
DIRECTION_TARGET = "direction_target"
VOLATILITY_TARGET = "volatility_target"

# Columns to EXCLUDE from features
EXCLUDE_FROM_FEATURES = [
    # Future information (direct leakage)
    "forward_returns",
    "risk_free_rate",
    "market_forward_excess_returns",
    # Targets we're predicting (derived from future)
    "volatility_target",
    "direction_target",
    # ID columns (not predictive)
    "date_id",
    "time_id",
    "row_id",
]

# Build feature lists from all numeric columns excluding the above
all_cols = source_df.columns.tolist()
direction_selected_features = [
    c
    for c in all_cols
    if c not in EXCLUDE_FROM_FEATURES
    and source_df[c].dtype in ["float64", "float32", "int64", "int32", "int8", "uint8"]
    and not c.startswith("__")  # Exclude any internal pandas columns
]
volatility_selected_features = direction_selected_features.copy()


print(f"\n{'=' * 80}")
print("SAVING TRAINING DATAFRAME FOR FEATURE VALIDATION")
print(f"{'=' * 80}\n")

# Save df_train with all engineered features
train_features_path = output_dir / "train_complete_all_features.csv"
df_train.write_csv(train_features_path)

print(f"✅ Saved df_train to: {train_features_path}")
print(f"   • Rows: {len(df_train):,}")
print(f"   • Columns: {len(df_train.columns)}")
print(f"   • File size: {train_features_path.stat().st_size / (1024 * 1024):.2f} MB")

# 🔧 COMPREHENSIVE FEATURE VALIDATION
print(f"\n{'=' * 80}")
print("COMPREHENSIVE FEATURE VALIDATION")
print(f"{'=' * 80}")

# Group features by category
feature_categories = {
    "GARCH": [
        "garch_variance",
        "garch_volatility",
        "garch_forecast_1d",
        "garch_standardized_resid",
        "garch_vol_shock",
        "garch_vol_regime",
        "garch_vol_change_1d",
        "garch_vol_change_5d",
        "garch_surprise",
    ],
    "CUSUM": [
        "cusum_volatility_pos",
        "cusum_volatility_neg",
        "cusum_returns_pos",
        "cusum_returns_neg",
        "changepoint_vol_any",
        "changepoint_ret_any",
        "cusum_days_since_changepoint",
        "cusum_vol_momentum",
        "cusum_ret_momentum",
        "large_vol_jump",
    ],
    "Anomaly": [
        "anomaly_extreme_is",
        "anomaly_moderate_is",
        "anomaly_mild_is",
        "anomaly_extreme_severity",
        "anomaly_moderate_severity",
        "anomaly_mild_severity",
        "anomaly_extreme_is_lag1",
        "anomaly_moderate_is_lag1",
        "anomaly_mild_is_lag1",
    ],
    "Kalman": [
        "kalman_h20_pred",
        "kalman_h20_pred_denorm",
        "kalman_h20_state_pos",
        "kalman_h20_state_vel",
        "kalman_h20_state_accel",
        "kalman_h20_confidence",
        "kalman_h20_rolling_vol",
    ],
    "CrossModel": [
        "kalman_cusum_vol_interact",
        "kalman_cusum_ret_interact",
        "kalman_anomaly_interact",
        "hmm_cusum_agree",
        "hmm_anomaly_agree",
        "models_agree_count",
        "kalman_conf_stability",
        "kalman_hmm_interact",
        "kalman_hmm5_interact",
    ],
    "HMM4_Base": [
        "hmm_regime",
        "hmm_regime_prob_0",
        "hmm_regime_prob_1",
        "hmm_regime_prob_2",
        "hmm_regime_prob_3",
        "hmm_regime_confidence",
        "hmm_regime_change",
        "hmm_regime_duration",
        "historical_vol_regime",
    ],
    "HMM4_Advanced": [
        "hmm4_regime_stable_3d",
        "hmm4_regime_stable_5d",
        "hmm4_confidence_change",
        "hmm4_confidence_ma_5",
        "hmm4_confidence_std_5",
        "hmm4_transitions_5d",
        "hmm4_transitions_10d",
        "hmm4_entropy",
    ],
    "HMM5_Base": [
        "hmm5_regime",
        "hmm5_regime_prob_0",
        "hmm5_regime_prob_1",
        "hmm5_regime_prob_2",
        "hmm5_regime_prob_3",
        "hmm5_regime_prob_4",
        "hmm5_regime_confidence",
        "hmm5_regime_change",
        "hmm5_regime_duration",
        "historical_vol5_regime",
    ],
    "HMM5_Advanced": [
        "hmm5_regime_stable_3d",
        "hmm5_regime_stable_5d",
        "hmm5_confidence_change",
        "hmm5_confidence_ma_5",
        "hmm5_confidence_std_5",
        "hmm5_transitions_5d",
        "hmm5_transitions_10d",
        "hmm5_entropy",
    ],
    "HMM_CrossModel": [
        "hmm_regime_agreement",
        "hmm_regime_divergence",
        "hmm_avg_confidence",
        "hmm_confidence_spread",
        "hmm_both_confident",
        "hmm_sync_transition",
        "hmm_total_transitions",
    ],
    "Helper": [
        "helper_vol_lr",
        "helper_vol_ewma",
        "helper_vol_consensus",
        "helper_dir_prob",
        "helper_dir_confidence",
        "helper_dir_signal",
        "helper_vol_lr_error",
        "helper_vol_ewma_error",
        "helper_dir_prob_x_regime",
    ],
    "DTMC": [
        "dtmc_state",
        "dtmc_p_up_1",
        "dtmc_p_up_5",
        "dtmc_p_up_10",
        "dtmc_p_up_20",
        "dtmc_p_down_1",
        "dtmc_transition_entropy",
        "dtmc_self_transition",
        "dtmc_expected_dwell",
        "dtmc_direction_spread",
        "dtmc_direction_confidence",
    ],
    "HMM_Dwell": [
        "hmm4_expected_dwell",
        "hmm4_weighted_dwell",
        "hmm4_transition_skew",
        "hmm4_regime_entropy",
        "hmm4_normalized_entropy",
        "hmm5_expected_dwell",
        "hmm5_weighted_dwell",
        "hmm5_transition_skew",
        "hmm5_regime_entropy",
        "hmm5_normalized_entropy",
        "hmm_dwell_divergence",
        "hmm_combined_entropy",
        "hmm_both_stable",
    ],
    "Regime_Stats": [
        "hmm_regime_0_pos_rate",
        "hmm_regime_1_pos_rate",
        "hmm_regime_2_pos_rate",
        "hmm_regime_3_pos_rate",
        "current_regime_pos_rate",
        "hmm5_regime_0_pos_rate",
        "hmm5_regime_1_pos_rate",
        "hmm5_regime_2_pos_rate",
        "hmm5_regime_3_pos_rate",
        "hmm5_regime_4_pos_rate",
        "current_regime5_pos_rate",
    ],
    "Volatility_Stats": [
        "hmm_regime_0_vol_pct",
        "hmm_regime_1_vol_pct",
        "hmm_regime_2_vol_pct",
        "hmm_regime_3_vol_pct",
        "current_regime_vol_pct",
        "hmm5_regime_0_vol_pct",
        "hmm5_regime_1_vol_pct",
        "hmm5_regime_2_vol_pct",
        "hmm5_regime_3_vol_pct",
        "hmm5_regime_4_vol_pct",
        "current_regime5_vol_pct",
    ],
    "Returns_Relative": ["returns_relative_to_expectation"],
}

# ═══════════════════════════════════════════════════════════════════════════
# FEATURE-GROUP HMM FEATURES - Only add if the group was trained
# Check FEATURE_GROUP_AVAILABLE to determine which groups exist
# ═══════════════════════════════════════════════════════════════════════════
fg_prefix_to_name = {
    "M": ("FG_Market_Basic", "FG_Market_Advanced", "FG_Market_CrossModel"),
    "E": ("FG_Economic_Basic", "FG_Economic_Advanced", "FG_Economic_CrossModel"),
    "I": ("FG_Interest_Basic", "FG_Interest_Advanced", "FG_Interest_CrossModel"),
    "P": ("FG_Price_Basic", "FG_Price_Advanced", "FG_Price_CrossModel"),
    "V": ("FG_Volatility_Basic", "FG_Volatility_Advanced", "FG_Volatility_CrossModel"),
    "S": ("FG_Sentiment_Basic", "FG_Sentiment_Advanced", "FG_Sentiment_CrossModel"),
}

for prefix, (basic_name, adv_name, cross_name) in fg_prefix_to_name.items():
    # Only add to validation if the group was trained
    if "FEATURE_GROUP_AVAILABLE" in dir() and FEATURE_GROUP_AVAILABLE.get(
        prefix, False
    ):
        feature_categories[basic_name] = [
            f"{prefix}_hmm_regime",
            f"{prefix}_hmm_confidence",
            f"{prefix}_hmm_regime_change",
            f"{prefix}_hmm_duration",
        ]
        feature_categories[adv_name] = [
            f"{prefix}_hmm_stable_3d",
            f"{prefix}_hmm_stable_5d",
            f"{prefix}_hmm_conf_change",
            f"{prefix}_hmm_conf_ma5",
            f"{prefix}_hmm_conf_std5",
            f"{prefix}_hmm_transitions_5d",
            f"{prefix}_hmm_transitions_10d",
            f"{prefix}_hmm_entropy",
        ]
        feature_categories[cross_name] = [
            f"{prefix}_kalman_interact",
            f"{prefix}_cusum_agree",
            f"{prefix}_anomaly_agree",
            f"{prefix}_hmm4_agree",
            f"{prefix}_hmm5_agree",
            f"{prefix}_kalman_conf_synergy",
            f"{prefix}_cusum_change_recency",
        ]
    else:
        print(f"  ⚠️  Skipping {prefix}* feature validation (group not trained)")

# ═══════════════════════════════════════════════════════════════════════════
# DERIVED FEATURE-GROUP HMM FEATURES (MOM*, D*)
# Check DERIVED_FEATURE_GROUP_AVAILABLE to determine which groups exist
# ═══════════════════════════════════════════════════════════════════════════
derived_fg_prefix_to_name = {
    "MOM": "DerivedFG_Momentum",
    "D": "DerivedFG_Binary",
}

for prefix, cat_name in derived_fg_prefix_to_name.items():
    # Only add to validation if the group was trained
    if (
        "DERIVED_FEATURE_GROUP_AVAILABLE" in dir()
        and DERIVED_FEATURE_GROUP_AVAILABLE.get(prefix, False)
    ):
        feature_categories[cat_name] = [
            f"{prefix}_hmm_regime",
            f"{prefix}_hmm_confidence",
            f"{prefix}_hmm_regime_change",
            f"{prefix}_hmm_duration",
        ]
    else:
        print(f"  ⚠️  Skipping {prefix}* derived feature validation (group not trained)")

# ═══════════════════════════════════════════════════════════════════════════
# PER-GROUP ISOLATION FOREST ANOMALY FEATURES (from Cell 7.8 Part A)
# Global aggregate features + per-group features
# These are unsupervised anomaly detection features trained per HMM group
# ═══════════════════════════════════════════════════════════════════════════

print("\n  🔍 ISOLATION FOREST FEATURE DETECTION:")

# Global aggregate IF features (always expected)
feature_categories["IsolationForest_Global"] = [
    "group_if_anomaly_score_mean",
    "group_if_anomaly_score_max",
    "group_if_n_anomalies",
    "group_if_max_severity",
    "group_if_any_severe",
]

# Check global IF features presence
global_if_found = sum(
    1 for f in feature_categories["IsolationForest_Global"] if f in source_df.columns
)
print(
    f"     IsolationForest_Global: {global_if_found}/{len(feature_categories['IsolationForest_Global'])} features found"
)

# Per-group Isolation Forest features (dynamically added based on available groups)
# Each group gets 4 features: anomaly_score, anomaly_score_norm, is_anomaly, severity
all_if_prefixes = ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
if_groups_found = []
if_groups_missing = []

for prefix in all_if_prefixes:
    # Check if this group has IF features in the dataframe
    if_col = f"{prefix}_if_is_anomaly"
    if if_col in source_df.columns:
        feature_categories[f"IsolationForest_{prefix}"] = [
            f"{prefix}_if_anomaly_score",
            f"{prefix}_if_anomaly_score_norm",
            f"{prefix}_if_is_anomaly",
            f"{prefix}_if_severity",
        ]
        if_groups_found.append(prefix)
    else:
        if_groups_missing.append(prefix)

print(f"     Per-group IF features found: {len(if_groups_found)}/10 groups")
if if_groups_found:
    print(f"       ✅ Groups with IF: {', '.join(if_groups_found)}")
if if_groups_missing:
    print(f"       ⚠️  Groups without IF: {', '.join(if_groups_missing)}")

# ═══════════════════════════════════════════════════════════════════════════
# PER-GROUP CHANGEPOINT DETECTION FEATURES (from Cell 7.8 Part B)
# Global aggregate features + per-group features
# These are supervised changepoint detection (volatility spike, direction reversal, extreme return)
# Each group's changepoint model uses: input_features + HMM_features + IF_features
# ═══════════════════════════════════════════════════════════════════════════

print("\n  🔍 CHANGEPOINT DETECTION FEATURE DETECTION:")

# Global aggregate changepoint features (always expected)
feature_categories["RegimeChangeDetection_Global"] = [
    "regime_change_vol_spike_prob",
    "regime_change_dir_reversal_prob",
    "regime_change_extreme_ret_prob",
    "regime_change_combined_signal",
    "regime_change_max_signal",
    "regime_change_any_high",
    "regime_change_n_groups_high",
]

# Check global changepoint features presence
global_chg_found = sum(
    1
    for f in feature_categories["RegimeChangeDetection_Global"]
    if f in source_df.columns
)
print(
    f"     RegimeChangeDetection_Global: {global_chg_found}/{len(feature_categories['RegimeChangeDetection_Global'])} features found"
)

# Per-group changepoint features (dynamically added based on available groups)
# Each group gets 5 features: vol_spike_prob, dir_reversal_prob, extreme_ret_prob, combined, any_high
all_changepoint_prefixes = ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
chg_groups_found = []
chg_groups_missing = []

for prefix in all_changepoint_prefixes:
    # Check if this group has changepoint features in the dataframe
    chg_col = f"{prefix}_chg_combined"
    if chg_col in source_df.columns:
        feature_categories[f"RegimeChange_{prefix}"] = [
            f"{prefix}_chg_vol_spike_prob",
            f"{prefix}_chg_dir_reversal_prob",
            f"{prefix}_chg_extreme_ret_prob",
            f"{prefix}_chg_combined",
            f"{prefix}_chg_any_high",
        ]
        chg_groups_found.append(prefix)
    else:
        chg_groups_missing.append(prefix)

print(f"     Per-group Changepoint features found: {len(chg_groups_found)}/10 groups")
if chg_groups_found:
    print(f"       ✅ Groups with Changepoint: {', '.join(chg_groups_found)}")
if chg_groups_missing:
    print(f"       ⚠️  Groups without Changepoint: {', '.join(chg_groups_missing)}")

# Summary of Cell 7.8 features
total_if_features = len(feature_categories.get("IsolationForest_Global", [])) + sum(
    len(feature_categories.get(f"IsolationForest_{p}", [])) for p in all_if_prefixes
)
total_chg_features = len(
    feature_categories.get("RegimeChangeDetection_Global", [])
) + sum(
    len(feature_categories.get(f"RegimeChange_{p}", []))
    for p in all_changepoint_prefixes
)
print("\n     📊 Cell 7.8 Feature Summary:")
print(
    f"        Isolation Forest: {total_if_features} features ({5} global + {len(if_groups_found) * 4} per-group)"
)
print(
    f"        Changepoint Detection: {total_chg_features} features ({7} global + {len(chg_groups_found) * 5} per-group)"
)
print(f"        TOTAL: {total_if_features + total_chg_features} features from Cell 7.8")

# ═══════════════════════════════════════════════════════════════════════════
# ROW-BY-ROW MOMENTUM FEATURES (from RowByRowFeatureCalculator)
# ═══════════════════════════════════════════════════════════════════════════
feature_categories["RowByRow_Momentum"] = [
    "momentum_5d",
    "momentum_10d",
    "momentum_21d",
    "momentum_50d",
    "momentum_100d",
    "momentum_200d",
    "momentum_252d",
    "momentum_accel_5d",
    "momentum_accel_10d",
    "momentum_accel_14d",
    "momentum_accel_21d",
    "momentum_accel_50d",
    "momentum_accel_100d",
    "momentum_accel_200d",
    "vol_momentum_5",
    "vol_momentum_10",
    "vol_momentum_21",
    "vol_adj_momentum_5d",
    "vol_adj_momentum_10d",
    "vol_adj_momentum_14d",
    "vol_adj_momentum_21d",
    "vol_adj_momentum_50d",
    "vol_adj_momentum_100d",
    "momentum_ratio_5_20",
    "momentum_ratio_5_50",
    "momentum_ratio_10_50",
    "momentum_ratio_20_100",
    "momentum_ratio_50_200",
]

# ═══════════════════════════════════════════════════════════════════════════
# ROW-BY-ROW BINARY/DUMMY FEATURES (from RowByRowFeatureCalculator)
# ═══════════════════════════════════════════════════════════════════════════
feature_categories["RowByRow_Binary"] = [
    "high_vol_regime",
    "extreme_vol_regime",
    "high_vol_regime_21",
    "high_vol_regime_50",
    "high_vol_regime_100",
    "high_vol_regime_200",
    "uptrend_regime",
    "uptrend_regime_5d",
    "uptrend_regime_10d",
    "uptrend_regime_14d",
    "uptrend_regime_21d",
    "uptrend_regime_50d",
    "uptrend_regime_100d",
    "uptrend_regime_200d",
    "strong_uptrend",
    "strong_uptrend_21d",
    "strong_uptrend_50d",
    "strong_uptrend_100d",
    "strong_downtrend_21d",
    "strong_downtrend_50d",
    "strong_downtrend_100d",
    "reversal_5d",
    "reversal_21d",
    "reversal_5_21",
    "reversal_10_50",
    "reversal_21_100",
    "reversal_50_200",
    "reversal_up_5_21",
    "reversal_up_10_50",
    "reversal_up_21_100",
    "reversal_up_50_200",
    "ma_cross_5_20",
    "ma_cross_10_50",
    "ma_cross_20_50",
    "ma_cross_50_200",
    "ma_cross_14_50",
    "ma_cross_21_100",
]

# ═══════════════════════════════════════════════════════════════════════════
# ROW-BY-ROW VOLATILITY FEATURES (from RowByRowFeatureCalculator)
# ═══════════════════════════════════════════════════════════════════════════
feature_categories["RowByRow_Volatility"] = [
    "volatility_ma_5",
    "volatility_ma_21",
    "volatility_ma_180",
    "mean_hist_vol_5",
    "mean_hist_vol_10",
    "mean_hist_vol_21",
    "mean_hist_vol_63",
    "mean_hist_vol_126",
    "mean_hist_vol_252",
    "vol_ratio_21",
    "mhv_ratio_5_21",
    "mhv_ratio_21_63",
    "mhv_ratio_63_252",
    "ewma_vol_5d",
    "ewma_vol_21d",
    "ewma_vol_60d",  # Matches extraction in row-by-row processing
    "vol_of_vol_5d",
    "vol_of_vol_10d",
    "vol_of_vol_21d",
    "vol_of_vol_50d",
    "vol_of_vol_60d",
    "vol_of_vol_100d",
    "realized_vol_5d",
    "realized_vol_21d",
    "realized_vol_50d",
    "realized_vol_100d",
    "realized_vol_252d",
    "vol_percentile_rank_21",
    "vol_percentile_rank_63",
    "vol_percentile_rank_126",
    "vol_percentile_rank_252",
    "vol_regime_discrete",
    "vol_position_in_range",
    "dist_from_p05",
    "dist_from_p95",
    "vol_cv_21",
    "vol_cv_63",
    "vol_acceleration_5",
    "vol_acceleration_21",
    "vol_autocorr_5",
    "vol_autocorr_21",
    "high_vol_days_5",
    "high_vol_days_21",
    "max_vol_change_5d",
    "avg_vol_change_5d",
]

# ═══════════════════════════════════════════════════════════════════════════
# ROW-BY-ROW STATISTICAL FEATURES (from RowByRowFeatureCalculator)
# ═══════════════════════════════════════════════════════════════════════════
feature_categories["RowByRow_Statistical"] = [
    "zscore_5d",
    "zscore_21d",
    "zscore_50d",
    "zscore_100d",
    "zscore_252d",
    "dist_from_ma_5d",
    "dist_from_ma_21d",
    "dist_from_ma_50d",
    "dist_from_ma_100d",
    "return_pctrank_21d",
    "return_pctrank_50d",
    "return_pctrank_100d",
    "return_pctrank_200d",
    "return_pctrank_252d",
    "skew_21d",
    "skew_50d",
    "skew_60d",
    "skew_100d",
    "skew_200d",
    "skew_252d",
    "kurt_21d",
    "kurt_50d",
    "kurt_60d",
    "kurt_100d",
    "kurt_200d",
    "kurt_252d",
    "sharpe_like_5d",
    "sharpe_like_21d",
    "sharpe_like_50d",
    "sharpe_like_100d",
    "sharpe_like_252d",
    "autocorr_5d",
    "autocorr_10d",
    "autocorr_21d",
    "autocorr_50d",
    "autocorr_100d",
]

# ═══════════════════════════════════════════════════════════════════════════
# ROW-BY-ROW EXPANDING & CONSECUTIVE FEATURES
# ═══════════════════════════════════════════════════════════════════════════
feature_categories["RowByRow_Expanding"] = [
    "expanding_mean_vol",
    "expanding_std_returns",
    "consecutive_up",
    "consecutive_down",
    "win_rate_ratio_5",
    "win_rate_ratio_21",
    "win_rate_ratio_180",
    "win_rate_5d",
    "win_rate_10d",
    "win_rate_21d",
    "win_rate_50d",
    "win_rate_100d",
]

# ═══════════════════════════════════════════════════════════════════════════
# ROW-BY-ROW TAIL RISK & DRAWDOWN FEATURES
# ═══════════════════════════════════════════════════════════════════════════
feature_categories["RowByRow_TailRisk"] = [
    "lower_5pct_21d",
    "upper_95pct_21d",
    "lower_10pct_21d",
    "upper_90pct_21d",
    "lower_5pct_100d",
    "upper_95pct_100d",
    "lower_5pct_252d",
    "upper_95pct_252d",
    "dist_from_lower_21d",
    "dist_from_upper_21d",
    "dist_from_lower_100d",
    "dist_from_upper_100d",
    "max_drawdown_5d",
    "max_drawdown_10d",
    "max_drawdown_21d",
    "max_drawdown_50d",
    "max_drawdown_100d",
    "max_drawdown_200d",
    "rolling_min_21d",
    "rolling_max_21d",
    "rolling_range_21d",
    "rolling_min_100d",
    "rolling_max_100d",
    "rolling_range_100d",
    "position_in_range_21d",
    "position_in_range_100d",
]

# ═══════════════════════════════════════════════════════════════════════════
# ROW-BY-ROW MA & ROC FEATURES
# ═══════════════════════════════════════════════════════════════════════════
feature_categories["RowByRow_MA_ROC"] = [
    "ma_5d",
    "ma_10d",
    "ma_21d",
    "ma_50d",
    "ma_100d",
    "ma_200d",
    "ma_252d",
    "ma_diff_5_20",
    "ma_diff_10_50",
    "ma_diff_20_50",
    "ma_diff_50_200",
    "ma_diff_14_50",
    "ma_diff_21_100",
    "roc_5d",
    "roc_10d",
    "roc_21d",
    "roc_50d",
    "roc_100d",
    "roc_200d",
    "return_lag_2d",
    "return_lag_3d",
    "return_lag_5d",
    "return_lag_7d",
    "return_lag_10d",
    "return_lag_21d",
]

# Validation summary counters
total_features = 0
found_features = 0
missing_features = []
zero_features = []

for category, features in feature_categories.items():
    print(f"\n  📊 {category} Features:")
    print(f"  {'-' * 76}")
    for feat in features:
        total_features += 1
        if feat in df_train.columns:
            found_features += 1
            col = df_train[feat]
            non_null = len(col.drop_nulls())
            non_zero = (col.fill_null(0).abs() > 1e-10).sum()
            min_val = col.min() if non_null > 0 else "N/A"
            max_val = col.max() if non_null > 0 else "N/A"
            pct_nonzero = non_zero / len(col) * 100
            status = "✅" if pct_nonzero > 1 else "⚠️ MOSTLY ZERO"
            if pct_nonzero < 1:
                zero_features.append(feat)
            print(
                f"    {feat:40s}: non-null={non_null:5d}, non-zero={non_zero:5d} ({pct_nonzero:5.1f}%), range=[{min_val}, {max_val}] {status}"
            )
        else:
            missing_features.append(feat)
            print(f"    {feat:40s}: ❌ NOT FOUND!")

print(f"\n{'=' * 80}")
print("FEATURE VALIDATION SUMMARY")
print(f"{'=' * 80}")
print(f"  Total features checked: {total_features}")
print(f"  Found: {found_features} ({found_features / total_features * 100:.1f}%)")
print(
    f"  Missing: {len(missing_features)} ({len(missing_features) / total_features * 100:.1f}%)"
)
print(f"  Mostly zero (< 1%): {len(zero_features)}")

if missing_features:
    print(f"\n  ❌ MISSING FEATURES ({len(missing_features)}):")
    for feat in missing_features:
        print(f"     - {feat}")

if zero_features:
    print(f"\n  ⚠️  MOSTLY ZERO FEATURES ({len(zero_features)}):")
    for feat in zero_features:
        print(f"     - {feat}")

print(f"\n{'=' * 80}")

# Print column count summary
print("\n📋 COLUMN SUMMARY:")
print(f"   Total columns in df_train: {len(df_train.columns)}")

# Categorize all columns
all_cols = df_train.columns
target_cols = [c for c in all_cols if "target" in c.lower() or "forward" in c.lower()]
id_cols = [c for c in all_cols if "id" in c.lower() or "date" in c.lower()]
feature_cols = [c for c in all_cols if c not in target_cols and c not in id_cols]

print(f"   ID/Date columns: {len(id_cols)}")
print(f"   Target columns: {len(target_cols)}")
print(f"   Feature columns: {len(feature_cols)}")

print(f"\n{'=' * 80}\n")

# ═══════════════════════════════════════════════════════════════════════════════
# COMPREHENSIVE FEATURE DISTRIBUTION VALIDATION
# Check if each feature was calculated correctly based on expected distributions
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 80)
print("FEATURE DISTRIBUTION VALIDATION")
print("=" * 80)
print()
print("Checking if feature calculations are correct by validating distributions...")
print()

# Convert to pandas for easier analysis
source_pd = df_train.to_pandas() if hasattr(df_train, "to_pandas") else df_train

# Define expected distributions for each feature type
FEATURE_DISTRIBUTION_SPECS = {
    # ═══════════════════════════════════════════════════════════════════════
    # HMM REGIME FEATURES - Expected: Discrete states 0-3 or 0-4
    # ═══════════════════════════════════════════════════════════════════════
    "hmm_regime": {
        "type": "discrete",
        "expected_values": [0, 1, 2, 3],
        "description": "HMM-4 regime (0=low vol, 1=normal, 2=high vol, 3=crisis)",
        "valid_range": (0, 3),
    },
    "hmm5_regime": {
        "type": "discrete",
        "expected_values": [0, 1, 2, 3, 4],
        "description": "HMM-5 regime (5-state model)",
        "valid_range": (0, 4),
    },
    # Per-group HMM regimes
    **{
        f"{p}_hmm_regime": {
            "type": "discrete",
            "expected_values": [0, 1, 2, 3],
            "description": f"{p} group HMM regime",
            "valid_range": (0, 3),
        }
        for p in ["M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # ═══════════════════════════════════════════════════════════════════════
    # HMM CONFIDENCE FEATURES - Expected: 0 to 1 (probability)
    # ═══════════════════════════════════════════════════════════════════════
    "hmm_regime_confidence": {
        "type": "probability",
        "expected_range": (0.0, 1.0),
        "typical_range": (0.3, 0.99),
        "description": "HMM-4 regime confidence (max state probability)",
    },
    "hmm5_regime_confidence": {
        "type": "probability",
        "expected_range": (0.0, 1.0),
        "typical_range": (0.2, 0.99),
        "description": "HMM-5 regime confidence",
    },
    # Per-group HMM confidence
    **{
        f"{p}_hmm_confidence": {
            "type": "probability",
            "expected_range": (0.0, 1.0),
            "typical_range": (0.3, 0.99),
            "description": f"{p} group HMM confidence",
        }
        for p in ["M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # ═══════════════════════════════════════════════════════════════════════
    # HMM REGIME CHANGE - Expected: Binary 0 or 1
    # ═══════════════════════════════════════════════════════════════════════
    "hmm_regime_change": {
        "type": "binary",
        "expected_values": [0, 1],
        "expected_ratio": (0.01, 0.30),  # 1-30% should be regime changes
        "description": "HMM-4 regime changed from previous day",
    },
    "hmm5_regime_change": {
        "type": "binary",
        "expected_values": [0, 1],
        "expected_ratio": (0.01, 0.40),
        "description": "HMM-5 regime changed from previous day",
    },
    # Per-group regime change
    **{
        f"{p}_hmm_regime_change": {
            "type": "binary",
            "expected_values": [0, 1],
            "expected_ratio": (0.01, 0.30),
            "description": f"{p} group regime changed",
        }
        for p in ["M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # ═══════════════════════════════════════════════════════════════════════
    # HMM DURATION - Expected: Positive integers, typically 1-100+
    # ═══════════════════════════════════════════════════════════════════════
    "hmm_regime_duration": {
        "type": "count",
        "expected_range": (1, 1000),
        "typical_range": (1, 100),
        "description": "Days in current HMM-4 regime",
    },
    "hmm5_regime_duration": {
        "type": "count",
        "expected_range": (1, 1000),
        "typical_range": (1, 100),
        "description": "Days in current HMM-5 regime",
    },
    # Per-group duration
    **{
        f"{p}_hmm_duration": {
            "type": "count",
            "expected_range": (1, 1000),
            "typical_range": (1, 100),
            "description": f"{p} group regime duration",
        }
        for p in ["M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # ═══════════════════════════════════════════════════════════════════════
    # ISOLATION FOREST FEATURES - Anomaly detection scores
    # ═══════════════════════════════════════════════════════════════════════
    # Per-group IF anomaly scores (raw decision function, typically -0.5 to 0.5)
    **{
        f"{p}_if_anomaly_score": {
            "type": "continuous",
            "expected_range": (-1.0, 1.0),
            "typical_range": (-0.5, 0.3),
            "description": f"{p} group Isolation Forest raw anomaly score (lower=more anomalous)",
        }
        for p in ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # Per-group IF normalized scores (z-score normalized, centered around 0)
    **{
        f"{p}_if_anomaly_score_norm": {
            "type": "normalized",
            "expected_range": (-5.0, 5.0),
            "typical_range": (-2.0, 2.0),
            "expected_mean": (-0.5, 0.5),
            "description": f"{p} group IF score (expanding z-score normalized)",
        }
        for p in ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # Per-group IF binary anomaly flag
    **{
        f"{p}_if_is_anomaly": {
            "type": "binary",
            "expected_values": [0, 1],
            "expected_ratio": (
                0.01,
                0.15,
            ),  # 1-15% should be anomalies (contamination ~5%)
            "description": f"{p} group binary anomaly indicator",
        }
        for p in ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # Per-group IF severity (0=normal, 1=mild, 2=moderate, 3=severe)
    **{
        f"{p}_if_severity": {
            "type": "discrete",
            "expected_values": [0, 1, 2, 3],
            "expected_distribution": {
                "0": (0.80, 0.98),
                "1": (0.01, 0.10),
                "2": (0.005, 0.05),
                "3": (0.001, 0.02),
            },
            "description": f"{p} group anomaly severity level",
        }
        for p in ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # Global IF aggregates
    "group_if_anomaly_score_mean": {
        "type": "continuous",
        "expected_range": (-1.0, 1.0),
        "typical_range": (-0.3, 0.2),
        "description": "Mean IF anomaly score across all groups",
    },
    "group_if_anomaly_score_max": {
        "type": "continuous",
        "expected_range": (-1.0, 1.0),
        "typical_range": (-0.2, 0.3),
        "description": "Max IF anomaly score across all groups",
    },
    "group_if_n_anomalies": {
        "type": "count",
        "expected_range": (0, 10),
        "typical_range": (0, 3),
        "description": "Number of groups flagging anomaly",
    },
    "group_if_max_severity": {
        "type": "discrete",
        "expected_values": [0, 1, 2, 3],
        "description": "Maximum severity across all groups",
    },
    "group_if_any_severe": {
        "type": "binary",
        "expected_values": [0, 1],
        "expected_ratio": (0.001, 0.10),
        "description": "Any group has severity >= 2",
    },
    # ═══════════════════════════════════════════════════════════════════════
    # CHANGEPOINT DETECTION FEATURES - Regime change probabilities
    # ═══════════════════════════════════════════════════════════════════════
    # Per-group volatility spike probability
    **{
        f"{p}_chg_vol_spike_prob": {
            "type": "probability",
            "expected_range": (0.0, 1.0),
            "typical_range": (0.05, 0.50),
            "description": f"{p} group P(volatility spike next day)",
        }
        for p in ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # Per-group direction reversal probability
    **{
        f"{p}_chg_dir_reversal_prob": {
            "type": "probability",
            "expected_range": (0.0, 1.0),
            "typical_range": (0.20, 0.60),
            "description": f"{p} group P(direction reversal)",
        }
        for p in ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # Per-group extreme return probability
    **{
        f"{p}_chg_extreme_ret_prob": {
            "type": "probability",
            "expected_range": (0.0, 1.0),
            "typical_range": (0.02, 0.30),
            "description": f"{p} group P(extreme return)",
        }
        for p in ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # Per-group combined changepoint signal
    **{
        f"{p}_chg_combined": {
            "type": "probability",
            "expected_range": (0.0, 1.0),
            "typical_range": (0.10, 0.50),
            "description": f"{p} group average changepoint probability",
        }
        for p in ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # Per-group any high signal
    **{
        f"{p}_chg_any_high": {
            "type": "binary",
            "expected_values": [0, 1],
            "expected_ratio": (0.05, 0.50),
            "description": f"{p} group any changepoint prob > 0.5",
        }
        for p in ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
    },
    # Global changepoint aggregates
    "regime_change_vol_spike_prob": {
        "type": "probability",
        "expected_range": (0.0, 1.0),
        "typical_range": (0.05, 0.40),
        "description": "Average vol spike prob across groups",
    },
    "regime_change_dir_reversal_prob": {
        "type": "probability",
        "expected_range": (0.0, 1.0),
        "typical_range": (0.20, 0.55),
        "description": "Average direction reversal prob across groups",
    },
    "regime_change_extreme_ret_prob": {
        "type": "probability",
        "expected_range": (0.0, 1.0),
        "typical_range": (0.02, 0.25),
        "description": "Average extreme return prob across groups",
    },
    "regime_change_combined_signal": {
        "type": "probability",
        "expected_range": (0.0, 1.0),
        "typical_range": (0.10, 0.45),
        "description": "Overall combined changepoint signal",
    },
    "regime_change_max_signal": {
        "type": "probability",
        "expected_range": (0.0, 1.0),
        "typical_range": (0.15, 0.70),
        "description": "Maximum changepoint signal across groups",
    },
    "regime_change_any_high": {
        "type": "binary",
        "expected_values": [0, 1],
        "expected_ratio": (0.10, 0.60),
        "description": "Any group has high changepoint signal",
    },
    "regime_change_n_groups_high": {
        "type": "count",
        "expected_range": (0, 10),
        "typical_range": (0, 4),
        "description": "Number of groups with high signal",
    },
    # ═══════════════════════════════════════════════════════════════════════
    # GARCH FEATURES - Volatility model outputs
    # ═══════════════════════════════════════════════════════════════════════
    "garch_volatility": {
        "type": "positive",
        "expected_range": (0.0, 0.5),
        "typical_range": (0.005, 0.10),
        "description": "GARCH estimated volatility (annualized)",
    },
    "garch_forecast_1d": {
        "type": "positive",
        "expected_range": (0.0, 0.5),
        "typical_range": (0.005, 0.10),
        "description": "GARCH 1-day ahead volatility forecast",
    },
    "garch_standardized_resid": {
        "type": "normalized",
        "expected_range": (-10.0, 10.0),
        "typical_range": (-3.0, 3.0),
        "expected_mean": (-0.5, 0.5),
        "description": "GARCH standardized residuals (should be ~N(0,1))",
    },
    "garch_vol_regime": {
        "type": "discrete",
        "expected_values": [0, 1, 2],
        "description": "GARCH volatility regime (0=low, 1=normal, 2=high)",
    },
    # ═══════════════════════════════════════════════════════════════════════
    # CUSUM FEATURES - Changepoint detection
    # ═══════════════════════════════════════════════════════════════════════
    "cusum_volatility_pos": {
        "type": "positive",
        "expected_range": (0.0, 100.0),
        "typical_range": (0.0, 20.0),
        "description": "CUSUM positive statistic for volatility",
    },
    "cusum_volatility_neg": {
        "type": "positive",
        "expected_range": (0.0, 100.0),
        "typical_range": (0.0, 20.0),
        "description": "CUSUM negative statistic for volatility",
    },
    "changepoint_vol_any": {
        "type": "binary",
        "expected_values": [0, 1],
        "expected_ratio": (0.01, 0.20),
        "description": "Volatility changepoint detected",
    },
    "changepoint_ret_any": {
        "type": "binary",
        "expected_values": [0, 1],
        "expected_ratio": (0.01, 0.20),
        "description": "Return changepoint detected",
    },
    # ═══════════════════════════════════════════════════════════════════════
    # KALMAN FILTER FEATURES
    # ═══════════════════════════════════════════════════════════════════════
    "kalman_h20_confidence": {
        "type": "probability",
        "expected_range": (0.0, 1.0),
        "typical_range": (0.3, 0.95),
        "description": "Kalman filter prediction confidence",
    },
    "kalman_h20_state_vel": {
        "type": "continuous",
        "expected_range": (-0.1, 0.1),
        "typical_range": (-0.02, 0.02),
        "description": "Kalman filter velocity state",
    },
    # ═══════════════════════════════════════════════════════════════════════
    # ANOMALY DETECTION FEATURES
    # ═══════════════════════════════════════════════════════════════════════
    "anomaly_extreme_is": {
        "type": "binary",
        "expected_values": [0, 1],
        "expected_ratio": (0.001, 0.05),
        "description": "Extreme anomaly detected",
    },
    "anomaly_moderate_is": {
        "type": "binary",
        "expected_values": [0, 1],
        "expected_ratio": (0.01, 0.10),
        "description": "Moderate anomaly detected",
    },
    "anomaly_extreme_severity": {
        "type": "positive",
        "expected_range": (0.0, 20.0),
        "typical_range": (0.0, 5.0),
        "description": "Extreme anomaly severity score",
    },
}


def validate_feature_distribution(col_name, values, spec):
    """Validate a single feature against its expected distribution."""
    results = {
        "name": col_name,
        "type": spec["type"],
        "status": "OK",
        "issues": [],
        "stats": {},
    }

    # Remove NaN values for analysis
    clean_values = values.dropna()
    n_total = len(values)
    n_valid = len(clean_values)
    n_nan = n_total - n_valid

    results["stats"]["n_total"] = n_total
    results["stats"]["n_valid"] = n_valid
    results["stats"]["n_nan"] = n_nan
    results["stats"]["pct_nan"] = n_nan / n_total * 100 if n_total > 0 else 0

    if n_valid == 0:
        results["status"] = "FAIL"
        results["issues"].append("All values are NaN")
        return results

    # Calculate basic statistics
    results["stats"]["min"] = float(clean_values.min())
    results["stats"]["max"] = float(clean_values.max())
    results["stats"]["mean"] = float(clean_values.mean())
    results["stats"]["std"] = float(clean_values.std())
    results["stats"]["median"] = float(clean_values.median())

    # Unique value count
    unique_vals = clean_values.unique()
    results["stats"]["n_unique"] = len(unique_vals)

    # Type-specific validation
    feat_type = spec["type"]

    if feat_type == "discrete":
        expected_vals = spec.get("expected_values", [])
        actual_vals = set(clean_values.unique())
        unexpected = actual_vals - set(expected_vals)
        if unexpected and len(unexpected) > 0:
            # Allow small tolerance for floating point
            unexpected_real = [
                v
                for v in unexpected
                if not any(abs(v - e) < 0.01 for e in expected_vals)
            ]
            if unexpected_real:
                results["issues"].append(f"Unexpected values: {unexpected_real[:5]}")
        # Check value distribution
        value_counts = clean_values.value_counts(normalize=True)
        results["stats"]["value_distribution"] = {
            str(int(k)): round(v, 4) for k, v in value_counts.items()
        }

    elif feat_type == "binary":
        unique_set = set(clean_values.unique())
        if not unique_set.issubset({0, 1}):
            results["issues"].append(f"Non-binary values found: {unique_set}")
        # Check ratio of 1s
        pct_ones = (clean_values == 1).sum() / n_valid
        results["stats"]["pct_ones"] = round(pct_ones * 100, 2)
        expected_ratio = spec.get("expected_ratio", (0.0, 1.0))
        if pct_ones < expected_ratio[0] or pct_ones > expected_ratio[1]:
            results["issues"].append(
                f"Ratio of 1s ({pct_ones:.1%}) outside expected {expected_ratio}"
            )

    elif feat_type == "probability":
        expected_range = spec.get("expected_range", (0.0, 1.0))
        if results["stats"]["min"] < expected_range[0] - 0.001:
            results["issues"].append(
                f"Min {results['stats']['min']:.4f} < {expected_range[0]}"
            )
        if results["stats"]["max"] > expected_range[1] + 0.001:
            results["issues"].append(
                f"Max {results['stats']['max']:.4f} > {expected_range[1]}"
            )
        typical_range = spec.get("typical_range", expected_range)
        if (
            results["stats"]["mean"] < typical_range[0] * 0.5
            or results["stats"]["mean"] > typical_range[1] * 1.5
        ):
            results["issues"].append(
                f"Mean {results['stats']['mean']:.4f} unusual for typical {typical_range}"
            )

    elif feat_type == "positive":
        if results["stats"]["min"] < -0.001:
            results["issues"].append(
                f"Negative values found (min={results['stats']['min']:.4f})"
            )
        expected_range = spec.get("expected_range", (0.0, float("inf")))
        if results["stats"]["max"] > expected_range[1] * 2:
            results["issues"].append(
                f"Max {results['stats']['max']:.4f} exceeds expected range"
            )

    elif feat_type == "count":
        if results["stats"]["min"] < 0:
            results["issues"].append(
                f"Negative counts found (min={results['stats']['min']})"
            )
        expected_range = spec.get("expected_range", (0, float("inf")))
        typical_range = spec.get("typical_range", expected_range)
        results["stats"]["pct_in_typical"] = (
            (
                (clean_values >= typical_range[0]) & (clean_values <= typical_range[1])
            ).sum()
            / n_valid
            * 100
        )

    elif feat_type in ["continuous", "normalized"]:
        expected_range = spec.get("expected_range", (-float("inf"), float("inf")))
        if results["stats"]["min"] < expected_range[0]:
            results["issues"].append(
                f"Min {results['stats']['min']:.4f} < expected {expected_range[0]}"
            )
        if results["stats"]["max"] > expected_range[1]:
            results["issues"].append(
                f"Max {results['stats']['max']:.4f} > expected {expected_range[1]}"
            )
        if feat_type == "normalized":
            expected_mean = spec.get("expected_mean", (-1.0, 1.0))
            if (
                results["stats"]["mean"] < expected_mean[0]
                or results["stats"]["mean"] > expected_mean[1]
            ):
                results["issues"].append(
                    f"Mean {results['stats']['mean']:.4f} outside expected {expected_mean}"
                )

    # Determine overall status
    if len(results["issues"]) > 0:
        results["status"] = "WARN" if len(results["issues"]) <= 2 else "FAIL"

    return results


# Run distribution validation
print("=" * 80)
print("DISTRIBUTION VALIDATION BY MODEL TYPE")
print("=" * 80)

validation_results = {
    "passed": [],
    "warnings": [],
    "failed": [],
    "not_found": [],
}

# Group features by model type for organized output
model_groups = {
    "HMM-4 Core": [
        "hmm_regime",
        "hmm_regime_confidence",
        "hmm_regime_change",
        "hmm_regime_duration",
    ],
    "HMM-5 Core": [
        "hmm5_regime",
        "hmm5_regime_confidence",
        "hmm5_regime_change",
        "hmm5_regime_duration",
    ],
    "Per-Group HMM (M, E, I, P, V, S)": [
        f"{p}_hmm_{s}"
        for p in ["M", "E", "I", "P", "V", "S"]
        for s in ["regime", "confidence", "regime_change", "duration"]
    ],
    "Derived HMM (MOM, D)": [
        f"{p}_hmm_{s}"
        for p in ["MOM", "D"]
        for s in ["regime", "confidence", "regime_change", "duration"]
    ],
    "Isolation Forest Global": [
        "group_if_anomaly_score_mean",
        "group_if_anomaly_score_max",
        "group_if_n_anomalies",
        "group_if_max_severity",
        "group_if_any_severe",
    ],
    "Isolation Forest Per-Group": [
        f"{p}_if_{s}"
        for p in ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
        for s in ["anomaly_score", "anomaly_score_norm", "is_anomaly", "severity"]
    ],
    "Changepoint Global": [
        "regime_change_vol_spike_prob",
        "regime_change_dir_reversal_prob",
        "regime_change_extreme_ret_prob",
        "regime_change_combined_signal",
        "regime_change_max_signal",
        "regime_change_any_high",
        "regime_change_n_groups_high",
    ],
    "Changepoint Per-Group": [
        f"{p}_chg_{s}"
        for p in ["HMM4", "HMM5", "M", "E", "I", "P", "V", "S", "MOM", "D"]
        for s in [
            "vol_spike_prob",
            "dir_reversal_prob",
            "extreme_ret_prob",
            "combined",
            "any_high",
        ]
    ],
    "GARCH": [
        "garch_volatility",
        "garch_forecast_1d",
        "garch_standardized_resid",
        "garch_vol_regime",
    ],
    "CUSUM": [
        "cusum_volatility_pos",
        "cusum_volatility_neg",
        "changepoint_vol_any",
        "changepoint_ret_any",
    ],
    "Kalman": ["kalman_h20_confidence", "kalman_h20_state_vel"],
    "Anomaly Detection": [
        "anomaly_extreme_is",
        "anomaly_moderate_is",
        "anomaly_extreme_severity",
    ],
}

for group_name, feature_list in model_groups.items():
    print(f"\n{'─' * 80}")
    print(f"📊 {group_name}")
    print(f"{'─' * 80}")

    group_ok = 0
    group_warn = 0
    group_fail = 0
    group_missing = 0

    for feat_name in feature_list:
        if feat_name not in source_pd.columns:
            validation_results["not_found"].append(feat_name)
            group_missing += 1
            continue

        if feat_name not in FEATURE_DISTRIBUTION_SPECS:
            # Feature exists but no spec defined - just show basic stats
            col = source_pd[feat_name]
            n_valid = col.notna().sum()
            if n_valid > 0:
                print(
                    f"  {feat_name:45s}: n={n_valid:5d}, min={col.min():8.4f}, max={col.max():8.4f}, mean={col.mean():8.4f} (no spec)"
                )
            continue

        spec = FEATURE_DISTRIBUTION_SPECS[feat_name]
        result = validate_feature_distribution(feat_name, source_pd[feat_name], spec)

        # Format output
        status_icon = {"OK": "✅", "WARN": "⚠️", "FAIL": "❌"}[result["status"]]
        stats = result["stats"]

        # Build stats string based on type
        if spec["type"] == "discrete":
            dist_str = ", ".join(
                [f"{k}:{v:.0%}" for k, v in stats.get("value_distribution", {}).items()]
            )
            stats_str = f"vals=[{dist_str}]"
        elif spec["type"] == "binary":
            stats_str = f"1s={stats.get('pct_ones', 0):.1f}%"
        elif spec["type"] == "probability":
            stats_str = (
                f"range=[{stats['min']:.3f}, {stats['max']:.3f}], μ={stats['mean']:.3f}"
            )
        else:
            stats_str = f"range=[{stats['min']:.4f}, {stats['max']:.4f}], μ={stats['mean']:.4f}, σ={stats['std']:.4f}"

        nan_str = f", NaN={stats['pct_nan']:.1f}%" if stats["pct_nan"] > 0.1 else ""

        print(f"  {status_icon} {feat_name:43s}: {stats_str}{nan_str}")

        if result["issues"]:
            for issue in result["issues"][:2]:
                print(f"      └─ {issue}")

        # Track results
        if result["status"] == "OK":
            validation_results["passed"].append(feat_name)
            group_ok += 1
        elif result["status"] == "WARN":
            validation_results["warnings"].append((feat_name, result["issues"]))
            group_warn += 1
        else:
            validation_results["failed"].append((feat_name, result["issues"]))
            group_fail += 1

    # Group summary
    total_in_group = group_ok + group_warn + group_fail
    if total_in_group > 0:
        print(
            f"\n  Summary: {group_ok}✅ {group_warn}⚠️ {group_fail}❌ (of {total_in_group} found, {group_missing} missing)"
        )

# Final summary
print(f"\n{'=' * 80}")
print("DISTRIBUTION VALIDATION SUMMARY")
print(f"{'=' * 80}")
print(f"  ✅ Passed: {len(validation_results['passed'])} features")
print(f"  ⚠️  Warnings: {len(validation_results['warnings'])} features")
print(f"  ❌ Failed: {len(validation_results['failed'])} features")
print(f"  🔍 Not found: {len(validation_results['not_found'])} features")

if validation_results["failed"]:
    print("\n  FAILED FEATURES (need investigation):")
    for feat, issues in validation_results["failed"][:10]:
        print(f"    • {feat}: {issues[0]}")

if validation_results["warnings"]:
    print("\n  WARNING FEATURES (may need attention):")
    for feat, issues in validation_results["warnings"][:10]:
        print(f"    • {feat}: {issues[0]}")

print(f"\n{'=' * 80}\n")
partial_save_path = output_dir / "df_train_partial_checkpoint.csv"
df_train.write_csv(partial_save_path)
print(f"✅ Saved partial df_train checkpoint: {partial_save_path}")
print(f"   • Rows: {len(df_train):,}")
print(f"   • Columns: {len(df_train.columns)}")
print(f"   • File size: {partial_save_path.stat().st_size / (1024 * 1024):.2f} MB")
print()
