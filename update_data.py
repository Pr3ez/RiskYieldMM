#!/usr/bin/env python3
"""One-command orchestrator for the core multi-asset data sources."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ORDER = ("bybit", "multiasset", "twelvedata", "databento", "yfinance")
CORE_SOURCE_ORDER = ("bybit", "multiasset")
DEFAULT_START_DATE = "2021-01-01"
DEFAULT_END_DATE = "now"
DEFAULT_MAX_TWELVE_REQUESTS = 2_000
DEFAULT_MAX_DATABENTO_COST_USD = 50.0


def _csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def selected_sources(raw: str) -> tuple[str, ...]:
    if not raw:
        return CORE_SOURCE_ORDER
    sources = _csv(raw)
    unknown = [source for source in sources if source not in SOURCE_ORDER]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"Unknown sources: {unknown}. Known sources: {', '.join(SOURCE_ORDER)}"
        )
    return tuple(source for source in SOURCE_ORDER if source in set(sources))


def _run_step(name: str, cmd: list[str], cwd: Path) -> bool:
    print("\n" + "=" * 70)
    print(name)
    print("=" * 70)
    print("Command:", " ".join(cmd))
    sys.stdout.flush()
    result = subprocess.run(cmd, cwd=str(cwd), check=False)
    return result.returncode == 0


def build_bybit_cmd(args: argparse.Namespace) -> tuple[list[str], Path]:
    cmd = [
        sys.executable,
        "update_data.py",
        "--fetch-only",
        "--start-date",
        args.start_date,
        "--end-date",
        args.end_date,
    ]
    if args.dry_run or args.estimate_only:
        cmd.append("--dry-run")
    return cmd, PROJECT_ROOT / "fetchingByBit"


def build_twelve_cmd(args: argparse.Namespace) -> tuple[list[str], Path]:
    cmd = [
        sys.executable,
        "update_data.py",
        "--providers",
        "twelvedata",
        "--core",
        "--htf-only",
        "--start-date",
        args.start_date,
        "--end-date",
        args.end_date,
        "--max-twelve-requests",
        str(args.max_twelve_requests),
    ]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.estimate_only:
        cmd.append("--estimate-only")
    return cmd, PROJECT_ROOT / "fetchingMultiAsset"


def build_databento_cmd(args: argparse.Namespace) -> tuple[list[str], Path]:
    cmd = [
        sys.executable,
        "update_data.py",
        "--providers",
        "databento",
        "--core",
        "--htf-only",
        "--start-date",
        args.start_date,
        "--end-date",
        args.end_date,
        "--max-databento-cost-usd",
        str(args.max_databento_cost_usd),
    ]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.estimate_only:
        cmd.append("--estimate-only")
    return cmd, PROJECT_ROOT / "fetchingMultiAsset"


def build_multiasset_cmd(args: argparse.Namespace) -> tuple[list[str], Path]:
    cmd = [
        sys.executable,
        "update_data.py",
        "--providers",
        "auto",
        "--core",
        "--htf-only",
        "--start-date",
        args.start_date,
        "--end-date",
        args.end_date,
        "--max-databento-cost-usd",
        str(args.max_databento_cost_usd),
    ]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.estimate_only:
        cmd.append("--estimate-only")
    return cmd, PROJECT_ROOT / "fetchingMultiAsset"


def build_yfinance_cmd(args: argparse.Namespace) -> tuple[list[str], Path]:
    cmd = [
        sys.executable,
        "update_data.py",
        "--providers",
        "yfinance",
        "--core",
        "--htf-only",
        "--end-date",
        args.end_date,
    ]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.estimate_only:
        cmd.append("--estimate-only")
    return cmd, PROJECT_ROOT / "fetchingMultiAsset"


def build_status_cmd(source: str) -> tuple[list[str], Path]:
    if source == "bybit":
        return [
            sys.executable,
            "update_data.py",
            "--status",
        ], PROJECT_ROOT / "fetchingByBit"
    provider = "auto" if source == "multiasset" else source
    return (
        [
            sys.executable,
            "update_data.py",
            "--providers",
            provider,
            "--core",
            "--htf-only",
            "--status",
        ],
        PROJECT_ROOT / "fetchingMultiAsset",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Core data update orchestrator: Bybit -> multi-asset auto source",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python update_data.py --core
  python update_data.py --core --dry-run
  python update_data.py --core --estimate-only
  python update_data.py --core --sources multiasset --dry-run
  python update_data.py --core --sources databento --estimate-only
  python update_data.py --core --sources yfinance --dry-run
  python update_data.py --core --sources twelvedata --start-date 2024-01-01 --end-date 2024-02-01
  python update_data.py --core --status
        """,
    )
    parser.add_argument(
        "--core",
        action="store_true",
        help="Run the intended core source mix in fixed order.",
    )
    parser.add_argument(
        "--sources",
        default="",
        help=(
            "Comma-separated subset. Default core order is bybit,multiasset. "
            "multiasset means Yahoo recent-tail first with Databento fallback. "
            "Twelve Data, Databento-only, and yfinance-only remain explicit sources."
        ),
    )
    parser.add_argument(
        "--allow-free-fresh-tail",
        action="store_true",
        help=(
            "Backward-compatible flag. Core uses Yahoo recent-tail automatically; "
            "with --sources databento it appends explicit yfinance after Databento."
        ),
    )
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE,
        help="Default matches original Bybit history start: 2021-01-01.",
    )
    parser.add_argument(
        "--end-date",
        default=DEFAULT_END_DATE,
        help="Default matches original Bybit history end: now.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="Preview/estimate without historical writes. Databento also prints costs.",
    )
    parser.add_argument(
        "--max-twelve-requests",
        type=int,
        default=DEFAULT_MAX_TWELVE_REQUESTS,
        help=(
            "Twelve Data request guard. Default is sized for the core full "
            "history backfill."
        ),
    )
    parser.add_argument(
        "--max-databento-cost-usd",
        type=float,
        default=DEFAULT_MAX_DATABENTO_COST_USD,
        help=(
            "Databento cost guard. Default is sized for the core full "
            "history estimate; lower it for smaller runs."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if not args.core:
        parser.error(
            "Use --core. Broad --all orchestration is intentionally unsupported."
        )

    sources = selected_sources(args.sources)
    if (
        args.allow_free_fresh_tail
        and "multiasset" not in sources
        and "yfinance" not in sources
    ):
        sources = tuple(
            source for source in SOURCE_ORDER if source in {*sources, "yfinance"}
        )
    started_at = datetime.now(timezone.utc)
    print("\n" + "=" * 70)
    print("CORE DATA UPDATE ORCHESTRATOR")
    print("=" * 70)
    print(f"Started: {started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Period: {args.start_date} -> {args.end_date}")
    print(f"Sources: {', '.join(sources)}")
    print("Order: Bybit crypto -> multi-asset auto source")
    if "multiasset" in sources:
        print("Multi-asset auto: Yahoo recent-tail first, Databento fallback if needed")
    if "twelvedata" in sources:
        print("Twelve Data selected explicitly as fallback/manual source")
    if "yfinance" in sources:
        print("Yahoo Finance selected as validated recent-tail source")
    sys.stdout.flush()

    success = True
    builders = {
        "bybit": build_bybit_cmd,
        "multiasset": build_multiasset_cmd,
        "twelvedata": build_twelve_cmd,
        "databento": build_databento_cmd,
        "yfinance": build_yfinance_cmd,
    }
    for source in sources:
        if args.status:
            cmd, cwd = build_status_cmd(source)
        else:
            cmd, cwd = builders[source](args)
        step_ok = _run_step(source.upper(), cmd, cwd)
        success = step_ok and success
        if not step_ok:
            print(f"ERROR: {source} step failed; stopping before later sources.")
            break

    ended_at = datetime.now(timezone.utc)
    print("\n" + "=" * 70)
    print("CORE DATA UPDATE COMPLETE")
    print("=" * 70)
    print(f"Duration: {(ended_at - started_at).total_seconds():.1f} seconds")
    print(f"Status: {'SUCCESS' if success else 'ERRORS OCCURRED'}")
    print("=" * 70 + "\n")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
