#!/bin/bash
# Automated data quality monitoring for Bybit market data
# Run this script daily via cron to ensure continuous data quality

# Configuration
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="$BASE_DIR/quality_reports"
DATE=$(date +%Y%m%d_%H%M%S)
SYMBOL="BTCUSDT"
CATEGORY="linear"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo "======================================================================="
echo "DATA QUALITY MONITORING - $DATE"
echo "======================================================================="
echo "Base Directory: $BASE_DIR"
echo "Symbol: $SYMBOL"
echo "Category: $CATEGORY"
echo ""

# Create report directory
mkdir -p "$REPORT_DIR"

# Run quality check
echo "[ 1/3 ] Running data quality validation..."
python3 "$BASE_DIR/data_quality_monitor.py" \
    --base-dir "$BASE_DIR" \
    --symbol "$SYMBOL" \
    --category "$CATEGORY" \
    --export-report "$REPORT_DIR/quality_$DATE.json"

EXIT_CODE=$?

echo ""
echo "======================================================================="

# Interpret results
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ DATA QUALITY: EXCELLENT${NC}"
    echo "No issues detected. Data is ready for model training."
    
elif [ $EXIT_CODE -eq 1 ]; then
    echo -e "${YELLOW}⚠ DATA QUALITY: WARNING${NC}"
    echo "Minor issues detected. Review the report for details."
    echo "Data may still be usable, but verify before production use."
    
    # Run gap analysis
    echo ""
    echo "[ 2/3 ] Analyzing gaps..."
    python3 "$BASE_DIR/gap_filler.py" \
        --base-dir "$BASE_DIR" \
        --symbol "$SYMBOL" \
        --category "$CATEGORY" \
        --dry-run \
        --export-report "$REPORT_DIR/gaps_$DATE.json"
    
else
    echo -e "${RED}❌ DATA QUALITY: CRITICAL${NC}"
    echo "Critical gaps or errors detected. Data is NOT ready for training."
    echo ""
    
    # Run gap analysis
    echo "[ 2/3 ] Analyzing gaps..."
    python3 "$BASE_DIR/gap_filler.py" \
        --base-dir "$BASE_DIR" \
        --symbol "$SYMBOL" \
        --category "$CATEGORY" \
        --dry-run \
        --export-report "$REPORT_DIR/gaps_$DATE.json"
    
    echo ""
    echo "RECOMMENDED ACTIONS:"
    echo "  1. Review gap report: $REPORT_DIR/gaps_$DATE.json"
    echo "  2. Re-run fetcher to fill gaps:"
    echo "     python3 $BASE_DIR/fetch_bybit_market_data.py"
    echo "  3. Re-run this monitoring script to verify fixes"
fi

echo "======================================================================="

# Generate summary report
echo ""
echo "[ 3/3 ] Generating summary..."

if [ -f "$REPORT_DIR/quality_$DATE.json" ]; then
    echo ""
    echo "SUMMARY STATISTICS:"
    python3 -c "
import json
import sys

try:
    with open('$REPORT_DIR/quality_$DATE.json') as f:
        report = json.load(f)
    
    summary = report.get('summary', {})
    print(f\"  Overall Status: {summary.get('overall_status', 'UNKNOWN')}\")
    print(f\"  Total Sources: {summary.get('total_sources', 0)}\")
    print(f\"  OK Sources: {summary.get('ok_sources', 0)}\")
    print(f\"  Incomplete: {summary.get('incomplete_sources', 0)}\")
    print(f\"  Missing: {summary.get('missing_sources', 0)}\")
    print(f\"  Total Gaps: {summary.get('total_gaps', 0)}\")
    print(f\"  Critical Issues: {summary.get('critical_issues', 0)}\")
    print(f\"  Warnings: {summary.get('warnings', 0)}\")
    
    # Check data freshness
    if 'klines_1h' in report.get('sources', {}):
        klines = report['sources']['klines_1h']
        if 'date_range' in klines:
            print(f\"\\n  Data Range:\")
            print(f\"    Start: {klines['date_range'].get('start', 'N/A')}\")
            print(f\"    End: {klines['date_range'].get('end', 'N/A')}\")
            print(f\"    Coverage: {klines.get('coverage_pct', 0):.2f}%\")

except Exception as e:
    print(f\"  Error reading report: {e}\", file=sys.stderr)
    sys.exit(1)
"
fi

echo ""
echo "REPORTS SAVED:"
echo "  Quality: $REPORT_DIR/quality_$DATE.json"
if [ -f "$REPORT_DIR/gaps_$DATE.json" ]; then
    echo "  Gaps: $REPORT_DIR/gaps_$DATE.json"
fi

# Cleanup old reports (keep last 30 days)
echo ""
echo "[ Maintenance ] Cleaning up old reports (>30 days)..."
OLD_REPORTS=$(find "$REPORT_DIR" -name "*.json" -mtime +30 2>/dev/null)
if [ -n "$OLD_REPORTS" ]; then
    echo "$OLD_REPORTS" | wc -l | xargs echo "  Removing reports:"
    find "$REPORT_DIR" -name "*.json" -mtime +30 -delete
else
    echo "  No old reports to clean"
fi

echo ""
echo "======================================================================="
echo "MONITORING COMPLETE - $(date)"
echo "======================================================================="

# Return appropriate exit code
exit $EXIT_CODE
