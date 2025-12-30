# Data Quality Quick Reference Card

## Daily Operations

### 1️⃣ Check Data Quality
```bash
cd /media/przem/linux_data/RiskYieldMM/fetchingByBit
./monitor_data_quality.sh
```
**Exit Codes:**
- `0` = ✅ Excellent (safe to train)
- `1` = ⚠️ Warnings (review before training)
- `2` = ❌ Critical (do not train, fix first)

---

### 2️⃣ Update Data (Daily)
```bash
cd /media/przem/linux_data/RiskYieldMM/fetchingByBit
python3 fetch_bybit_market_data.py
```
**Time:** 5-15 minutes for daily updates (resumable if interrupted)

---

### 3️⃣ Validate After Update
```bash
python3 data_quality_monitor.py
```
**Expected:** "Overall Status: EXCELLENT" with 0 gaps

---

## Gap Detection & Fixing

### Detect Gaps
```bash
python3 gap_filler.py --dry-run
```

### If Gaps Found
```bash
# Option 1: Re-run fetcher (automatic gap filling)
python3 fetch_bybit_market_data.py

# Option 2: Targeted fetch (edit START_DATE/END_DATE in script first)
# nano fetch_bybit_market_data.py  # Set date range
python3 fetch_bybit_market_data.py
```

---

## Before Training Models

### Pre-Training Checklist
```bash
# 1. Validate data
python3 data_quality_monitor.py --export-report pre_training_check.json

# 2. Check for gaps
python3 gap_filler.py --dry-run

# 3. Verify date range
python3 -c "
import json
with open('pre_training_check.json') as f:
    report = json.load(f)
print('Date Range:', report['sources']['klines_1h']['date_range'])
print('Coverage:', report['sources']['klines_1h']['coverage_pct'], '%')
print('Status:', report['summary']['overall_status'])
"
```

**Proceed with training only if:**
- ✅ Status = EXCELLENT
- ✅ Coverage ≥ 99.5%
- ✅ Total gaps = 0

---

## Monitoring Logs

### View Current Fetch Progress
```bash
tail -f fetch_log_*.log
```

### Check Latest Progress State
```bash
cat .fetch_progress.json | jq '.'
```

### View Recent Quality Reports
```bash
ls -lh quality_reports/*.json | tail -5
```

---

## Common Issues

### "API rate limit exceeded"
**Solution:** Wait 60 seconds, script will auto-retry

### "Network timeout"
**Solution:** Check internet, re-run script (resumable)

### "Gaps detected after fetch"
**Cause:** Bybit API missing data for specific periods
**Solution:** 
1. Document the gap period
2. Try re-fetching after 24 hours
3. If persistent, it's likely exchange downtime

### "Timestamp misalignment"
**Cause:** Different sources updated at different times
**Solution:** Re-run all fetches with all `FETCH_*` flags enabled

---

## Quick Stats

### Data Size Estimates (per year, BTCUSDT)
- 1-minute: ~500 MB
- 5-minute: ~100 MB
- 1-hour: ~10 MB
- Daily: ~0.5 MB
- Funding: ~0.5 MB
- OI/Mark/Index: ~10 MB each

### Fetch Times (2021-present)
- Initial full fetch: 20-30 hours
- Daily update: 5-15 minutes

---

## Automation Setup

### Cron Job for Daily Updates & Monitoring
```bash
# Edit crontab
crontab -e

# Add these lines:

# Update data daily at 1 AM
0 1 * * * cd /media/przem/linux_data/RiskYieldMM/fetchingByBit && python3 fetch_bybit_market_data.py >> cron.log 2>&1

# Check quality daily at 3 AM
0 3 * * * cd /media/przem/linux_data/RiskYieldMM/fetchingByBit && ./monitor_data_quality.sh >> quality_cron.log 2>&1
```

---

## Emergency Procedures

### Data Corruption Detected
```bash
# 1. Backup current data
cp -r fetchingByBit fetchingByBit_backup_$(date +%Y%m%d)

# 2. Identify corrupted source
python3 data_quality_monitor.py --export-report corruption_check.json
cat corruption_check.json | jq '.sources | to_entries[] | select(.value.status != "OK")'

# 3. Delete corrupted files (example for 1h klines)
rm -rf sorted-1h-bybit-linear/

# 4. Re-fetch
python3 fetch_bybit_market_data.py

# 5. Validate
python3 data_quality_monitor.py
```

### Start Fresh (Nuclear Option)
```bash
# ⚠️ WARNING: Deletes all data!
rm -rf sorted-* funding-* open-interest-* mark-price-* index-price-* premium-price-*
rm .fetch_progress.json
python3 fetch_bybit_market_data.py
```

---

## Integration with Python

### Check Data Quality in Code
```python
import subprocess
import sys

# Run validation
result = subprocess.run(
    ["python3", "data_quality_monitor.py", "--export-report", "check.json"],
    cwd="/media/przem/linux_data/RiskYieldMM/fetchingByBit"
)

if result.returncode != 0:
    print("❌ Data quality check failed")
    sys.exit(1)

# Load report
import json
with open("/media/przem/linux_data/RiskYieldMM/fetchingByBit/check.json") as f:
    quality = json.load(f)

assert quality["summary"]["overall_status"] == "EXCELLENT", "Data not ready"
assert quality["summary"]["total_gaps"] == 0, "Gaps detected"

print("✅ Data validated - proceeding with training")
```

---

## Support Files

- 📖 **Full Documentation:** `DATA_QUALITY_README.md`
- 🔧 **Main Fetcher:** `fetch_bybit_market_data.py`
- ✅ **Quality Monitor:** `data_quality_monitor.py`
- 🔍 **Gap Detector:** `gap_filler.py`
- 🤖 **Auto Monitor:** `monitor_data_quality.sh`
- 📊 **Data Guide:** `DATA_SOURCES_EXPLAINED.md`

---

## Status Indicators

### EXCELLENT ✅
- All sources complete
- No gaps
- Coverage 100%
- Ready for production

### WARNING ⚠️
- Minor issues detected
- Coverage 95-99%
- Review before production

### CRITICAL ❌
- Gaps detected
- Coverage <95%
- Do NOT use for training

---

**Remember:** One hour of missing data can invalidate weeks of model training. Always validate before training.
