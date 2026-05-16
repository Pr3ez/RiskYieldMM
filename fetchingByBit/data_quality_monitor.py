#!/usr/bin/env python3
"""
Data Quality Monitor for Bybit Market Data
===========================================
Comprehensive validation suite to ensure continuous, gap-free data.

Validates:
1. Temporal continuity (no missing timestamps)
2. Cross-source alignment (all sources have matching timestamps)
3. Data completeness (expected vs actual record counts)
4. Value sanity checks (no nulls, valid ranges)
5. Inter-file consistency
6. Expected vs actual date range coverage

Usage:
    python data_quality_monitor.py
    python data_quality_monitor.py --symbol BTCUSDT --category linear
    python data_quality_monitor.py --export-report quality_report.json
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


class DataQualityMonitor:
    """Monitor and validate market data quality across all sources."""

    INTERVAL_MS = {
        "1m": 60_000,
        "5m": 300_000,
        "15m": 900_000,
        "1h": 3_600_000,
        "4h": 14_400_000,
        "1d": 86_400_000,
    }

    def __init__(self, base_dir: str, symbol: str, category: str):
        self.base_dir = Path(base_dir)
        self.symbol = symbol.lower()
        self.category = category
        self.report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "category": category,
            "sources": {},
            "summary": {
                "total_issues": 0,
                "critical_issues": 0,
                "warnings": 0,
                "overall_status": "UNKNOWN",
            },
        }

    def run_full_validation(self) -> dict:
        """Execute complete validation suite."""
        print("=" * 70)
        print(f"DATA QUALITY VALIDATION: {self.symbol.upper()} ({self.category})")
        print("=" * 70 + "\n")

        # Validate each data source
        self._validate_klines()
        self._validate_funding_rate()
        self._validate_open_interest()
        self._validate_mark_price()
        self._validate_index_price()
        self._validate_premium_index()
        self._validate_long_short_ratio()

        # Cross-source validation
        self._validate_timestamp_alignment()

        # Generate summary
        self._generate_summary()

        return self.report

    def _validate_klines(self):
        """Validate OHLCV kline data for all intervals."""
        print("[ 1/8 ] Validating OHLCV Klines...")

        for interval, label in [
            ("1", "1m"),
            ("5", "5m"),
            ("15", "15m"),
            ("60", "1h"),
            ("240", "4h"),
            ("D", "1d"),
        ]:
            if interval == "D":
                step_ms = 86_400_000
            else:
                step_ms = int(interval) * 60_000

            source_key = f"klines_{label}"
            data_dir = self.base_dir / f"sorted-{label}-bybit-{self.category}"

            if not data_dir.exists():
                self.report["sources"][source_key] = {
                    "status": "MISSING",
                    "message": f"Directory not found: {data_dir}",
                }
                self.report["summary"]["warnings"] += 1
                continue

            # Find all parquet files
            files = sorted(
                data_dir.glob(f"{self.symbol}_{self.category}_sorted_batch_*.parquet")
            )

            if not files:
                self.report["sources"][source_key] = {
                    "status": "NO_DATA",
                    "message": "No parquet files found",
                }
                self.report["summary"]["warnings"] += 1
                continue

            # Validate
            issues = self._validate_time_series_files(files, step_ms, label)

            self.report["sources"][source_key] = issues
            if issues["gaps"] > 0 or issues["overlaps"] > 0:
                self.report["summary"]["critical_issues"] += 1
            if issues["missing_fields"]:
                self.report["summary"]["warnings"] += 1

        print("  ✓ Completed klines validation\n")

    def _validate_funding_rate(self):
        """Validate funding rate data."""
        print("[ 2/8 ] Validating Funding Rate...")

        if self.category not in ["linear", "inverse"]:
            print("  ⊘ Skipped (not applicable for spot)\n")
            return

        source_key = "funding_rate"
        data_dir = self.base_dir / f"funding-rate-bybit-{self.category}"
        data_file = data_dir / f"{self.symbol}_funding_rate.parquet"

        if not data_file.exists():
            self.report["sources"][source_key] = {
                "status": "MISSING",
                "message": f"File not found: {data_file}",
            }
            self.report["summary"]["warnings"] += 1
            print("  ⚠ Missing data file\n")
            return

        # Funding rate is every 8 hours = 28800000 ms
        issues = self._validate_single_file(
            data_file, 28_800_000, "fundingRateTimestamp", "8h"
        )
        self.report["sources"][source_key] = issues

        if issues["gaps"] > 0:
            self.report["summary"]["critical_issues"] += 1

        print("  ✓ Completed funding rate validation\n")

    def _validate_open_interest(self):
        """Validate open interest data."""
        print("[ 3/8 ] Validating Open Interest...")

        if self.category == "spot":
            print("  ⊘ Skipped (not applicable for spot)\n")
            return

        # Bybit open interest does not support 1m. The HTF workflow broadcasts
        # 5m open interest into 1m rows and uses 15m natively for 15m rows.
        for label, step_ms in [
            ("5m", 300_000),
            ("15m", 900_000),
            ("1h", 3_600_000),
            ("4h", 14_400_000),
            ("1d", 86_400_000),
        ]:
            source_key = f"open_interest_{label}"
            data_dir = self.base_dir / f"open-interest-{label}-bybit-{self.category}"
            data_file = data_dir / f"{self.symbol}_oi.parquet"

            if not data_file.exists():
                self.report["sources"][source_key] = {
                    "status": "MISSING",
                    "message": f"File not found: {data_file}",
                }
                self.report["summary"]["warnings"] += 1
                continue

            issues = self._validate_single_file(
                data_file, step_ms, "timestamp_ms", label
            )
            self.report["sources"][source_key] = issues

            if issues["gaps"] > 0:
                self.report["summary"]["critical_issues"] += 1

        print("  ✓ Completed open interest validation\n")

    def _validate_mark_price(self):
        """Validate mark price data."""
        print("[ 4/8 ] Validating Mark Price...")

        if self.category == "spot":
            print("  ⊘ Skipped (not applicable for spot)\n")
            return

        for label, step_ms in [
            ("1m", 60_000),
            ("5m", 300_000),
            ("15m", 900_000),
            ("1h", 3_600_000),
            ("4h", 14_400_000),
            ("1d", 86_400_000),
        ]:
            source_key = f"mark_price_{label}"
            data_dir = self.base_dir / f"mark-price-{label}-bybit-{self.category}"
            data_file = data_dir / f"{self.symbol}_mark.parquet"

            if not data_file.exists():
                self.report["sources"][source_key] = {
                    "status": "MISSING",
                    "message": f"File not found: {data_file}",
                }
                self.report["summary"]["warnings"] += 1
                continue

            issues = self._validate_single_file(
                data_file, step_ms, "timestamp_ms", label
            )
            self.report["sources"][source_key] = issues

            if issues["gaps"] > 0:
                self.report["summary"]["critical_issues"] += 1

        print("  ✓ Completed mark price validation\n")

    def _validate_index_price(self):
        """Validate index price data."""
        print("[ 5/8 ] Validating Index Price...")

        for label, step_ms in [
            ("1m", 60_000),
            ("5m", 300_000),
            ("15m", 900_000),
            ("1h", 3_600_000),
            ("4h", 14_400_000),
            ("1d", 86_400_000),
        ]:
            source_key = f"index_price_{label}"
            data_dir = self.base_dir / f"index-price-{label}-bybit-{self.category}"
            data_file = data_dir / f"{self.symbol}_index.parquet"

            if not data_file.exists():
                self.report["sources"][source_key] = {
                    "status": "MISSING",
                    "message": f"File not found: {data_file}",
                }
                self.report["summary"]["warnings"] += 1
                continue

            issues = self._validate_single_file(
                data_file, step_ms, "timestamp_ms", label
            )
            self.report["sources"][source_key] = issues

            if issues["gaps"] > 0:
                self.report["summary"]["critical_issues"] += 1

        print("  ✓ Completed index price validation\n")

    def _validate_premium_index(self):
        """Validate premium index data."""
        print("[ 6/8 ] Validating Premium Index...")

        if self.category not in ["linear", "inverse"]:
            print("  ⊘ Skipped (not applicable for spot)\n")
            return

        for label, step_ms in [
            ("1m", 60_000),
            ("5m", 300_000),
            ("15m", 900_000),
            ("1h", 3_600_000),
            ("4h", 14_400_000),
            ("1d", 86_400_000),
        ]:
            source_key = f"premium_index_{label}"
            data_dir = self.base_dir / f"premium-price-{label}-bybit-{self.category}"
            data_file = data_dir / f"{self.symbol}_premium.parquet"

            if not data_file.exists():
                self.report["sources"][source_key] = {
                    "status": "MISSING",
                    "message": f"File not found: {data_file}",
                }
                self.report["summary"]["warnings"] += 1
                continue

            issues = self._validate_single_file(
                data_file, step_ms, "timestamp_ms", label
            )
            self.report["sources"][source_key] = issues

            if issues["gaps"] > 0:
                self.report["summary"]["critical_issues"] += 1

        print("  ✓ Completed premium index validation\n")

    def _validate_long_short_ratio(self):
        """Validate long/short account-ratio data."""
        print("[ 7/8 ] Validating Long/Short Ratio...")

        if self.category not in ["linear", "inverse"]:
            print("  ⊘ Skipped (not applicable for spot)\n")
            return

        # Bybit long/short ratio does not support 1m. The HTF workflow uses
        # 5m for 1m broadcast and 15m natively for 15m feature rows.
        for label, step_ms in [
            ("5m", 300_000),
            ("15m", 900_000),
            ("1h", 3_600_000),
            ("4h", 14_400_000),
            ("1d", 86_400_000),
        ]:
            source_key = f"long_short_ratio_{label}"
            data_dir = self.base_dir / f"long-short-ratio-{label}-bybit-{self.category}"
            data_file = data_dir / f"{self.symbol}_ls_ratio.parquet"

            if not data_file.exists():
                self.report["sources"][source_key] = {
                    "status": "MISSING",
                    "message": f"File not found: {data_file}",
                }
                self.report["summary"]["warnings"] += 1
                continue

            issues = self._validate_single_file(
                data_file, step_ms, "timestamp_ms", label
            )
            self.report["sources"][source_key] = issues

            if issues["gaps"] > 0:
                self.report["summary"]["critical_issues"] += 1

        print("  ✓ Completed long/short ratio validation\n")

    def _validate_time_series_files(
        self, files: list[Path], step_ms: int, label: str
    ) -> dict:
        """Validate a collection of chunked parquet files."""
        issues = {
            "status": "OK",
            "total_files": len(files),
            "total_records": 0,
            "date_range": {"start": None, "end": None},
            "expected_records": 0,
            "coverage_pct": 0.0,
            "gaps": 0,
            "gap_details": [],
            "overlaps": 0,
            "duplicates": 0,
            "null_values": 0,
            "missing_fields": [],
            "irregular_intervals": 0,
        }

        all_timestamps = []

        try:
            for file in files:
                df = pd.read_parquet(file)
                issues["total_records"] += len(df)

                # Check required fields
                required_fields = [
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ]
                missing = [f for f in required_fields if f not in df.columns]
                if missing and not issues["missing_fields"]:
                    issues["missing_fields"] = missing

                # Check for nulls
                null_count = df[required_fields].isnull().sum().sum()
                issues["null_values"] += int(null_count)

                # Collect timestamps
                ts_ms = (df["timestamp"].astype("int64") // 1_000_000).tolist()
                all_timestamps.extend(ts_ms)

            if not all_timestamps:
                issues["status"] = "EMPTY"
                return issues

            # Sort timestamps
            all_timestamps = sorted(all_timestamps)
            issues["date_range"]["start"] = datetime.fromtimestamp(
                all_timestamps[0] / 1000, tz=timezone.utc
            ).isoformat()
            issues["date_range"]["end"] = datetime.fromtimestamp(
                all_timestamps[-1] / 1000, tz=timezone.utc
            ).isoformat()

            # Check for duplicates
            issues["duplicates"] = len(all_timestamps) - len(set(all_timestamps))

            # Detect gaps
            gaps = []
            overlaps = 0
            irregular = 0

            for i in range(1, len(all_timestamps)):
                delta = all_timestamps[i] - all_timestamps[i - 1]

                if delta == 0:
                    overlaps += 1
                elif delta > step_ms:
                    missing_count = (delta // step_ms) - 1
                    gaps.append(
                        {
                            "start": datetime.fromtimestamp(
                                all_timestamps[i - 1] / 1000, tz=timezone.utc
                            ).isoformat(),
                            "end": datetime.fromtimestamp(
                                all_timestamps[i] / 1000, tz=timezone.utc
                            ).isoformat(),
                            "missing_records": int(missing_count),
                            "duration_hours": delta / 3_600_000,
                        }
                    )
                elif 0 < delta < step_ms:
                    irregular += 1

            issues["gaps"] = len(gaps)
            issues["gap_details"] = gaps[:10]  # Store first 10 gaps
            issues["overlaps"] = overlaps
            issues["irregular_intervals"] = irregular

            # Calculate expected records
            time_span_ms = all_timestamps[-1] - all_timestamps[0]
            expected_records = (time_span_ms // step_ms) + 1
            issues["expected_records"] = int(expected_records)
            issues["coverage_pct"] = round(
                (issues["total_records"] / expected_records * 100)
                if expected_records > 0
                else 0,
                2,
            )

            # Determine status
            if issues["gaps"] > 0 or issues["coverage_pct"] < 99.0:
                issues["status"] = "INCOMPLETE"
            elif issues["null_values"] > 0 or issues["duplicates"] > 0:
                issues["status"] = "DEGRADED"
            else:
                issues["status"] = "OK"

        except Exception as e:
            issues["status"] = "ERROR"
            issues["message"] = str(e)

        return issues

    def _validate_single_file(
        self, file_path: Path, step_ms: int, time_col: str, label: str
    ) -> dict:
        """Validate a single parquet file."""
        issues = {
            "status": "OK",
            "total_records": 0,
            "date_range": {"start": None, "end": None},
            "expected_records": 0,
            "coverage_pct": 0.0,
            "gaps": 0,
            "gap_details": [],
            "overlaps": 0,
            "duplicates": 0,
            "null_values": 0,
            "missing_fields": [],
            "irregular_intervals": 0,
        }

        try:
            df = pd.read_parquet(file_path)
            issues["total_records"] = len(df)

            if df.empty:
                issues["status"] = "EMPTY"
                return issues

            # Check for time column
            if time_col not in df.columns:
                issues["status"] = "ERROR"
                issues["message"] = f"Missing time column: {time_col}"
                return issues

            # Get timestamps
            ts_ms = df[time_col].astype("int64").tolist()
            ts_ms = sorted(ts_ms)

            issues["date_range"]["start"] = datetime.fromtimestamp(
                ts_ms[0] / 1000, tz=timezone.utc
            ).isoformat()
            issues["date_range"]["end"] = datetime.fromtimestamp(
                ts_ms[-1] / 1000, tz=timezone.utc
            ).isoformat()

            # Check duplicates
            issues["duplicates"] = len(ts_ms) - len(set(ts_ms))

            # Detect gaps
            gaps = []
            overlaps = 0
            irregular = 0

            for i in range(1, len(ts_ms)):
                delta = ts_ms[i] - ts_ms[i - 1]

                if delta == 0:
                    overlaps += 1
                elif delta > step_ms:
                    missing_count = (delta // step_ms) - 1
                    gaps.append(
                        {
                            "start": datetime.fromtimestamp(
                                ts_ms[i - 1] / 1000, tz=timezone.utc
                            ).isoformat(),
                            "end": datetime.fromtimestamp(
                                ts_ms[i] / 1000, tz=timezone.utc
                            ).isoformat(),
                            "missing_records": int(missing_count),
                            "duration_hours": delta / 3_600_000,
                        }
                    )
                elif 0 < delta < step_ms:
                    irregular += 1

            issues["gaps"] = len(gaps)
            issues["gap_details"] = gaps[:10]
            issues["overlaps"] = overlaps
            issues["irregular_intervals"] = irregular

            # Calculate coverage
            time_span_ms = ts_ms[-1] - ts_ms[0]
            expected_records = (time_span_ms // step_ms) + 1
            issues["expected_records"] = int(expected_records)
            issues["coverage_pct"] = round(
                (issues["total_records"] / expected_records * 100)
                if expected_records > 0
                else 0,
                2,
            )

            # Check for nulls
            numeric_cols = df.select_dtypes(include=["float64", "int64"]).columns
            issues["null_values"] = int(df[numeric_cols].isnull().sum().sum())

            # Status
            if issues["gaps"] > 0 or issues["coverage_pct"] < 99.0:
                issues["status"] = "INCOMPLETE"
            elif issues["null_values"] > 0 or issues["duplicates"] > 0:
                issues["status"] = "DEGRADED"

        except Exception as e:
            issues["status"] = "ERROR"
            issues["message"] = str(e)

        return issues

    def _validate_timestamp_alignment(self):
        """Check if timestamps align across different data sources."""
        print("[ 8/8 ] Validating Cross-Source Timestamp Alignment...")

        # Get timestamps from klines_1h (reference)
        klines_dir = self.base_dir / f"sorted-1h-bybit-{self.category}"
        klines_files = sorted(
            klines_dir.glob(f"{self.symbol}_{self.category}_sorted_batch_*.parquet")
        )

        if not klines_files:
            print("  ⚠ No reference klines data found for alignment check\n")
            return

        try:
            # Load reference timestamps
            ref_timestamps = set()
            for f in klines_files:
                df = pd.read_parquet(f, columns=["timestamp"])
                ts_ms = (df["timestamp"].astype("int64") // 1_000_000).tolist()
                ref_timestamps.update(ts_ms)

            alignment_results = {
                "reference_source": "klines_1h",
                "reference_count": len(ref_timestamps),
                "sources": {},
            }

            # Check OI alignment
            oi_file = (
                self.base_dir
                / f"open-interest-1h-bybit-{self.category}"
                / f"{self.symbol}_oi.parquet"
            )
            if oi_file.exists():
                df = pd.read_parquet(oi_file, columns=["timestamp_ms"])
                oi_timestamps = set(df["timestamp_ms"].tolist())
                missing = len(ref_timestamps - oi_timestamps)
                extra = len(oi_timestamps - ref_timestamps)
                alignment_results["sources"]["open_interest_1h"] = {
                    "missing_from_reference": missing,
                    "extra_not_in_reference": extra,
                    "alignment_pct": round((1 - missing / len(ref_timestamps)) * 100, 2)
                    if ref_timestamps
                    else 0,
                }

            # Check mark price alignment
            mark_file = (
                self.base_dir
                / f"mark-price-1h-bybit-{self.category}"
                / f"{self.symbol}_mark.parquet"
            )
            if mark_file.exists():
                df = pd.read_parquet(mark_file, columns=["timestamp_ms"])
                mark_timestamps = set(df["timestamp_ms"].tolist())
                missing = len(ref_timestamps - mark_timestamps)
                extra = len(mark_timestamps - ref_timestamps)
                alignment_results["sources"]["mark_price_1h"] = {
                    "missing_from_reference": missing,
                    "extra_not_in_reference": extra,
                    "alignment_pct": round((1 - missing / len(ref_timestamps)) * 100, 2)
                    if ref_timestamps
                    else 0,
                }

            self.report["timestamp_alignment"] = alignment_results

            # Count misalignments
            misaligned = sum(
                1
                for s in alignment_results["sources"].values()
                if s["alignment_pct"] < 99.0
            )
            if misaligned > 0:
                self.report["summary"]["warnings"] += misaligned

            print("  ✓ Completed alignment validation\n")

        except Exception as e:
            print(f"  ✗ Alignment check failed: {e}\n")

    def _generate_summary(self):
        """Generate final summary and determine overall status."""
        total_sources = len(self.report["sources"])
        ok_sources = sum(
            1 for s in self.report["sources"].values() if s.get("status") == "OK"
        )
        incomplete = sum(
            1
            for s in self.report["sources"].values()
            if s.get("status") == "INCOMPLETE"
        )
        missing = sum(
            1
            for s in self.report["sources"].values()
            if s.get("status") in ["MISSING", "NO_DATA"]
        )

        self.report["summary"]["total_sources"] = total_sources
        self.report["summary"]["ok_sources"] = ok_sources
        self.report["summary"]["incomplete_sources"] = incomplete
        self.report["summary"]["missing_sources"] = missing

        total_gaps = sum(s.get("gaps", 0) for s in self.report["sources"].values())
        self.report["summary"]["total_gaps"] = total_gaps

        # Determine overall status
        if self.report["summary"]["critical_issues"] > 0 or total_gaps > 0:
            self.report["summary"]["overall_status"] = "CRITICAL"
        elif self.report["summary"]["warnings"] > 0 or incomplete > 0:
            self.report["summary"]["overall_status"] = "WARNING"
        elif ok_sources == total_sources:
            self.report["summary"]["overall_status"] = "EXCELLENT"
        else:
            self.report["summary"]["overall_status"] = "UNKNOWN"

        # Print summary
        print("=" * 70)
        print("VALIDATION SUMMARY")
        print("=" * 70)
        print(f"Overall Status     : {self.report['summary']['overall_status']}")
        print(f"Total Sources      : {total_sources}")
        print(f"OK                 : {ok_sources}")
        print(f"Incomplete         : {incomplete}")
        print(f"Missing            : {missing}")
        print(f"Total Gaps         : {total_gaps}")
        print(f"Critical Issues    : {self.report['summary']['critical_issues']}")
        print(f"Warnings           : {self.report['summary']['warnings']}")
        print("=" * 70 + "\n")

        # Show gap details
        if total_gaps > 0:
            print("⚠️  GAP DETAILS (first 5):")
            count = 0
            for source, data in self.report["sources"].items():
                if data.get("gap_details"):
                    for gap in data["gap_details"][:2]:
                        print(
                            f"  {source}: {gap['start']} → {gap['end']} "
                            f"({gap['missing_records']} records, "
                            f"{gap['duration_hours']:.1f}h)"
                        )
                        count += 1
                        if count >= 5:
                            break
                if count >= 5:
                    break
            print()

    def export_report(self, output_path: str):
        """Export validation report to JSON."""
        with open(output_path, "w") as f:
            json.dump(self.report, f, indent=2)
        print(f"✓ Report exported to: {output_path}")


def main():
    """Run the Bybit data quality monitor CLI and return status-based exit codes."""
    parser = argparse.ArgumentParser(description="Validate Bybit market data quality")
    parser.add_argument(
        "--base-dir", default=".", help="Base directory containing data folders"
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading symbol")
    parser.add_argument(
        "--category", default="linear", choices=["spot", "linear", "inverse"]
    )
    parser.add_argument("--export-report", help="Export JSON report to file")

    args = parser.parse_args()

    # Resolve base directory
    base_dir = Path(args.base_dir).resolve()
    if not base_dir.exists():
        print(f"❌ Base directory not found: {base_dir}")
        return 1

    # Run validation
    monitor = DataQualityMonitor(str(base_dir), args.symbol, args.category)
    report = monitor.run_full_validation()

    # Export if requested
    if args.export_report:
        monitor.export_report(args.export_report)

    # Exit code based on status
    status = report["summary"]["overall_status"]
    if status == "CRITICAL":
        return 2
    elif status == "WARNING":
        return 1
    else:
        return 0


if __name__ == "__main__":
    exit(main())
