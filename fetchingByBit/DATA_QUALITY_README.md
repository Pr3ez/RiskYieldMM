# Data Quality Monitoring System

## Overview

This directory contains a comprehensive data quality monitoring system to ensure continuous, gap-free market data collection from Bybit. Training ML models on incomplete or inaccurate data leads to poor performance in production. This system prevents that.

## Critical Importance

**Why Data Quality Matters:**
- **Missing timestamps** → Model learns incorrect temporal patterns
- **Data gaps** → Biased feature distributions, incorrect volatility estimates
- **Misaligned sources** → Feature engineering fails, indicators calculate wrong values
- **Duplicates/overlaps** → Data leakage, inflated performance metrics
- **Null values** → Model training failures or silent degradation

**One hour of missing data can invalidate weeks of model training.**

## System Components

### 1. fetch_bybit_market_data.py
**Purpose:** Primary data fetcher with built-in quality controls

**Features:**
- ✅ Resumable downloads (survives interruptions)
- ✅ Forward pagination (oldest → newest)
- ✅ Automatic integrity verification
- ✅ Progress tracking with JSON state file
- ✅ Comprehensive logging to timestamped log files
- ✅ Error handling with automatic retries
- ✅ Rate limit respect

**Configuration:**
```python
# Edit these in the script
SYMBOLS    = ["BTCUSDT", "ETHUSDT"]
CATEGORY   = "linear"  # spot | linear | inverse
START_DATE = "2021-01-01"
END_DATE   = "now"

# Toggle data sources
FETCH_KLINES         = True
FETCH_FUNDING_RATE   = True
FETCH_OPEN_INTEREST  = True
FETCH_MARK_PRICE     = True
FETCH_INDEX_PRICE    = True
FETCH_PREMIUM_INDEX  = True
```

**Usage:**
```bash
# Run the fetcher
python fetch_bybit_market_data.py

# Monitor progress
tail -f fetch_log_*.log

# Check progress state
cat .fetch_progress.json
```

**Output Structure:**
```
fetchingByBit/
├── sorted-1m-bybit-linear/       # 1-minute OHLCV klines
│   ├── btcusdt_linear_sorted_batch_000000.parquet
│   ├── ethusdt_linear_sorted_batch_000000.parquet
│   └── ...
├── sorted-5m-bybit-linear/       # 5-minute klines
├── sorted-15m-bybit-linear/      # 15-minute klines
├── sorted-1h-bybit-linear/       # 1-hour klines
├── sorted-4h-bybit-linear/       # 4-hour klines
├── sorted-1d-bybit-linear/       # Daily klines
├── funding-rate-bybit-linear/    # Funding rate (8h snapshots)
│   └── btcusdt_funding_rate.parquet
├── open-interest-1h-bybit-linear/  # Open interest per interval
│   └── btcusdt_oi.parquet
├── mark-price-1h-bybit-linear/   # Mark price per interval
│   └── btcusdt_mark.parquet
├── index-price-1h-bybit-linear/  # Index price per interval
│   └── btcusdt_index.parquet
└── premium-price-1h-bybit-linear/  # Premium index per interval
    └── btcusdt_premium.parquet
```

### 2. data_quality_monitor.py
**Purpose:** Comprehensive validation suite

**Validates:**
- ✅ Temporal continuity (no missing timestamps)
- ✅ Expected vs actual record counts
- ✅ Gap detection with precise location and duration
- ✅ Duplicate detection
- ✅ Null value checking
- ✅ Cross-file boundary consistency
- ✅ Timestamp alignment across data sources
- ✅ Data completeness percentage

**Usage:**
```bash
# Run full validation
python data_quality_monitor.py

# Specify symbol/category
python data_quality_monitor.py --symbol ETHUSDT --category linear

# Export JSON report
python data_quality_monitor.py --export-report quality_report.json

# Check specific base directory
python data_quality_monitor.py --base-dir /path/to/data
```

**Exit Codes:**
- `0` = EXCELLENT (no issues)
- `1` = WARNING (minor issues, data usable)
- `2` = CRITICAL (gaps found, data incomplete)

**Sample Output:**
```
======================================================================
DATA QUALITY VALIDATION: BTCUSDT (linear)
======================================================================

[ 1/7 ] Validating OHLCV Klines...
  ✓ Completed klines validation

[ 2/7 ] Validating Funding Rate...
  ✓ Completed funding rate validation

[ 3/7 ] Validating Open Interest...
  ✓ Completed open interest validation

[ 4/7 ] Validating Mark Price...
  ✓ Completed mark price validation

[ 5/7 ] Validating Index Price...
  ✓ Completed index price validation

[ 6/7 ] Validating Premium Index...
  ✓ Completed premium index validation

[ 7/7 ] Validating Cross-Source Timestamp Alignment...
  ✓ Completed alignment validation

======================================================================
VALIDATION SUMMARY
======================================================================
Overall Status     : EXCELLENT
Total Sources      : 36
OK                 : 36
Incomplete         : 0
Missing            : 0
Total Gaps         : 0
Critical Issues    : 0
Warnings           : 0
======================================================================
```

**JSON Report Structure:**
```json
{
  "timestamp": "2025-01-15T10:30:00Z",
  "symbol": "BTCUSDT",
  "category": "linear",
  "sources": {
    "klines_1h": {
      "status": "OK",
      "total_records": 35040,
      "expected_records": 35040,
      "coverage_pct": 100.0,
      "gaps": 0,
      "overlaps": 0,
      "duplicates": 0,
      "date_range": {
        "start": "2021-01-01T00:00:00Z",
        "end": "2025-01-15T00:00:00Z"
      }
    }
  },
  "timestamp_alignment": {
    "reference_source": "klines_1h",
    "sources": {
      "open_interest_1h": {
        "alignment_pct": 99.98
      }
    }
  },
  "summary": {
    "overall_status": "EXCELLENT",
    "total_gaps": 0
  }
}
```

### 3. gap_filler.py
**Purpose:** Automated gap detection and reporting

**Features:**
- ✅ Scans all data sources for gaps
- ✅ Groups gaps by source and severity
- ✅ Calculates missing record counts
- ✅ Estimates gap duration in hours/days
- ✅ Exports detailed gap reports
- ✅ Dry-run mode for safe analysis

**Usage:**
```bash
# Detect gaps without fixing (recommended first step)
python gap_filler.py --dry-run

# Show gaps for specific source
python gap_filler.py --source klines_1h --dry-run

# Export gap report
python gap_filler.py --export-report gap_analysis.json

# Specify symbol/category
python gap_filler.py --symbol ETHUSDT --category linear --dry-run
```

**Sample Output:**
```
======================================================================
SCANNING FOR DATA GAPS
======================================================================

⚠️  FOUND 3 GAPS:

  klines_1h: 2 gaps
    • Missing records: 24
    • Total duration: 24.0 hours (1.0 days)
    • 2024-12-10 14:00:00 → 2024-12-10 20:00:00 (6 records)
    • 2024-12-25 08:00:00 → 2024-12-26 02:00:00 (18 records)

  open_interest_1h: 1 gaps
    • Missing records: 12
    • Total duration: 12.0 hours (0.5 days)
    • 2024-12-15 09:00:00 → 2024-12-15 21:00:00 (12 records)
```

## Workflow: Ensuring Data Quality

### Initial Data Collection

```bash
# Step 1: Start the fetcher
python fetch_bybit_market_data.py

# Step 2: Monitor progress (in another terminal)
tail -f fetch_log_*.log

# Step 3: Wait for completion (can take hours for full historical data)
```

### Regular Validation (Run Daily)

```bash
# Step 1: Run quality monitor
python data_quality_monitor.py --export-report daily_check_$(date +%Y%m%d).json

# Step 2: Check exit code
if [ $? -eq 0 ]; then
    echo "✓ Data quality excellent"
elif [ $? -eq 1 ]; then
    echo "⚠ Minor issues detected"
else
    echo "❌ Critical gaps found - re-run fetcher"
fi

# Step 3: If issues found, analyze gaps
python gap_filler.py --dry-run --export-report gaps_$(date +%Y%m%d).json
```

### Fixing Gaps

If gaps are detected:

```bash
# Option 1: Re-run the fetcher (it's resumable and will fill gaps)
python fetch_bybit_market_data.py

# Option 2: For targeted gaps, manually set START_DATE/END_DATE
# Edit fetch_bybit_market_data.py:
# START_DATE = "2024-12-10"  # Start of gap
# END_DATE = "2024-12-26"    # End of gap
python fetch_bybit_market_data.py

# Option 3: Validate after filling
python data_quality_monitor.py
```

### Automated Monitoring Script

Create `monitor_data_quality.sh`:

```bash
#!/bin/bash
# Automated data quality monitoring

BASE_DIR="/media/przem/linux_data/RiskYieldMM/fetchingByBit"
REPORT_DIR="$BASE_DIR/quality_reports"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$REPORT_DIR"

# Run quality check
python "$BASE_DIR/data_quality_monitor.py" \
    --base-dir "$BASE_DIR" \
    --export-report "$REPORT_DIR/quality_$DATE.json"

EXIT_CODE=$?

# Send alert if critical issues
if [ $EXIT_CODE -eq 2 ]; then
    echo "CRITICAL: Data gaps detected at $DATE" | mail -s "Data Quality Alert" your@email.com
    
    # Run gap analysis
    python "$BASE_DIR/gap_filler.py" \
        --base-dir "$BASE_DIR" \
        --dry-run \
        --export-report "$REPORT_DIR/gaps_$DATE.json"
fi

# Cleanup old reports (keep last 30 days)
find "$REPORT_DIR" -name "*.json" -mtime +30 -delete

exit $EXIT_CODE
```

Schedule with cron:
```bash
# Run daily at 2 AM
0 2 * * * /path/to/monitor_data_quality.sh
```

## Data Quality Checklist

Before training models, verify:

- [ ] **Temporal Continuity**: No gaps in timestamps
  ```bash
  python data_quality_monitor.py | grep "Total Gaps"
  # Should show: Total Gaps: 0
  ```

- [ ] **Coverage**: ≥99% of expected records
  ```bash
  python data_quality_monitor.py --export-report check.json
  jq '.sources[] | select(.coverage_pct < 99)' check.json
  # Should return empty
  ```

- [ ] **Alignment**: All sources have matching timestamps
  ```bash
  jq '.timestamp_alignment.sources[] | select(.alignment_pct < 99)' check.json
  # Should return empty
  ```

- [ ] **No Duplicates**: Unique timestamps only
  ```bash
  jq '.sources[] | select(.duplicates > 0)' check.json
  # Should return empty
  ```

- [ ] **No Nulls**: All numeric fields populated
  ```bash
  jq '.sources[] | select(.null_values > 0)' check.json
  # Should return empty
  ```

- [ ] **Date Range**: Covers intended training period
  ```bash
  jq '.sources.klines_1h.date_range' check.json
  # Verify start/end dates match requirements
  ```

## Common Issues and Solutions

### Issue: "Gaps detected in klines_1h"
**Cause:** Network interruption during initial fetch, or Bybit API returned incomplete data

**Solution:**
```bash
# Re-run fetcher (it's resumable)
python fetch_bybit_market_data.py

# Verify fix
python data_quality_monitor.py
```

### Issue: "Timestamp misalignment between sources"
**Cause:** Different data sources fetched at different times

**Solution:**
```bash
# Ensure all sources are enabled in fetch_bybit_market_data.py
# Set all FETCH_* flags to True
# Re-run fetcher
python fetch_bybit_market_data.py

# Focus on specific intervals that need alignment
```

### Issue: "Coverage percentage below 99%"
**Cause:** Bybit API didn't return data for specific periods (exchange downtime, delisting, etc.)

**Solution:**
```bash
# Check gap details
python gap_filler.py --dry-run

# If gaps are during known exchange outages, document them
# If gaps are unexpected, re-fetch those periods
```

### Issue: "Duplicates detected"
**Cause:** Overlapping fetches or timestamp precision issues

**Solution:**
```bash
# The fetcher has built-in deduplication
# Re-run to clean up:
python fetch_bybit_market_data.py

# If persists, manually remove duplicate files and re-fetch
```

## Performance Metrics

**Expected Fetch Times (BTCUSDT linear, 2021-01-01 to now):**
- 1-minute klines: ~6-8 hours
- 5-minute klines: ~2-3 hours
- 1-hour klines: ~30-45 minutes
- Daily klines: ~5-10 minutes
- Funding rate: ~10-15 minutes
- Open interest (all intervals): ~2-3 hours
- Mark/Index/Premium (all intervals): ~2-3 hours each

**Total: ~20-30 hours for complete historical dataset**

**Validation Times:**
- Quality monitor: ~2-5 minutes
- Gap detection: ~1-2 minutes

## Integration with ML Pipeline

### Before Feature Engineering
```python
import subprocess
import sys

# Validate data quality
result = subprocess.run(
    ["python", "data_quality_monitor.py", "--export-report", "pre_training_check.json"],
    capture_output=True
)

if result.returncode != 0:
    print("❌ Data quality check failed - cannot proceed with training")
    sys.exit(1)

# Load quality report
import json
with open("pre_training_check.json") as f:
    quality = json.load(f)

if quality["summary"]["overall_status"] != "EXCELLENT":
    print(f"⚠ Data quality: {quality['summary']['overall_status']}")
    print(f"Gaps: {quality['summary']['total_gaps']}")
    sys.exit(1)

print("✓ Data quality validated - proceeding with feature engineering")
```

### Continuous Monitoring
```python
# Add to model training script
import os
from datetime import datetime, timedelta

def check_data_freshness(base_dir: str, max_age_hours: int = 24):
    """Ensure data is recent enough for production use."""
    progress_file = os.path.join(base_dir, ".fetch_progress.json")
    
    if not os.path.exists(progress_file):
        raise ValueError("No fetch progress found - run fetcher first")
    
    with open(progress_file) as f:
        progress = json.load(f)
    
    # Check latest update
    latest = max(v["last_update"] for v in progress.values())
    latest_dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
    age_hours = (datetime.now(timezone.utc) - latest_dt).total_seconds() / 3600
    
    if age_hours > max_age_hours:
        raise ValueError(f"Data is {age_hours:.1f} hours old - refresh required")
    
    return True
```

## Files Generated

```
fetchingByBit/
├── fetch_bybit_market_data.py      # Main fetcher
├── data_quality_monitor.py         # Validation suite
├── gap_filler.py                   # Gap detection
├── DATA_QUALITY_README.md          # This file
├── fetch_log_YYYYMMDD_HHMMSS.log  # Timestamped logs
├── .fetch_progress.json            # Progress state
└── quality_reports/                # Validation reports
    ├── quality_YYYYMMDD.json
    └── gaps_YYYYMMDD.json
```

## Best Practices

1. **Always validate before training**
   - Run `data_quality_monitor.py` before every training session
   - Store validation reports with model artifacts

2. **Monitor data freshness**
   - For production models, ensure data is updated daily
   - Set up automated monitoring with alerting

3. **Document known gaps**
   - If gaps are due to exchange issues, document them
   - Track which periods are missing and why

4. **Version your data**
   - Keep quality reports timestamped
   - Associate model versions with specific data snapshots

5. **Test on subset first**
   - Before fetching years of data, test on a week
   - Validate the process works end-to-end

6. **Backup progress files**
   - Save `.fetch_progress.json` regularly
   - Helps recover from interruptions

## Troubleshooting

### Fetcher stops unexpectedly
- Check `fetch_log_*.log` for errors
- Verify internet connection
- Check Bybit API status: https://bybit-exchange.github.io/docs/v5/rate-limit
- Resume by running fetcher again (it's resumable)

### Validation takes too long
- Validation scales with data volume
- For large datasets (1m data over 4+ years), expect 5-10 minutes
- Run with `--source` to validate specific sources

### Out of disk space
- 1-minute data is largest: ~500MB per year
- Monitor disk usage: `df -h`
- Disable unnecessary intervals if space constrained

## Support and Contact

For issues or questions:
1. Check log files in `fetchingByBit/fetch_log_*.log`
2. Run quality monitor to diagnose: `python data_quality_monitor.py`
3. Review gap report: `python gap_filler.py --dry-run`

**Remember:** Good data quality is the foundation of reliable models. Invest time in validation now to avoid costly mistakes later.
