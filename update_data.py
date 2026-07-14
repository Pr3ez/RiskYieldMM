#!/usr/bin/env python3
"""One-command orchestrator for the core multi-asset data sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ANALYST_ROOT = PROJECT_ROOT / "Risk_Yield_Meta_Model_Analyst_0_0_1"
SOURCE_ORDER = ("bybit", "multiasset", "twelvedata", "databento", "yfinance")
CORE_SOURCE_ORDER = ("bybit", "multiasset")
DEMO_SOURCE_ORDER = ("bybit", "yfinance")
DEFAULT_START_DATE = "2021-01-01"
DEFAULT_END_DATE = "now"
DEFAULT_MAX_TWELVE_REQUESTS = 2_000
DEFAULT_MAX_DATABENTO_COST_USD = 50.0
DEFAULT_CANONICAL_ASSETS = "core"
DEFAULT_DERIVED_CANONICAL_TIMEFRAMES = "15m,1h,4h,8h,12h,1d"
DEFAULT_LIVE_TIMEFRAMES = "1m,15m,1h,4h,8h,12h,1d"
DEFAULT_LIVE_ASSETS = "core"
DEMO_YFINANCE_1M_LIMIT = timedelta(days=7)


def _csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def selected_sources(raw: str) -> tuple[str, ...]:
    """Normalize the repo-level source list while preserving pipeline order."""
    if not raw:
        return CORE_SOURCE_ORDER
    sources = _csv(raw)
    unknown = [source for source in sources if source not in SOURCE_ORDER]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"Unknown sources: {unknown}. Known sources: {', '.join(SOURCE_ORDER)}"
        )
    return tuple(source for source in SOURCE_ORDER if source in set(sources))


def _parse_cli_datetime(
    value: str | datetime, *, now: datetime | None = None
) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if raw.lower() in {"now", "today"}:
            dt = now or datetime.now(timezone.utc)
        else:
            normalized = raw.replace("Z", "+00:00")
            if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
                dt = datetime.strptime(normalized, "%Y-%m-%d")
            else:
                dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_cli_datetime(dt: datetime) -> str:
    return (
        dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def resolve_demo_window(
    end_date: str | datetime = DEFAULT_END_DATE,
    *,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Return the latest Yahoo-safe 1m demo window as CLI date strings."""
    end = _parse_cli_datetime(end_date, now=now).replace(second=0, microsecond=0)
    # Use the last complete minute so Bybit and Yahoo receive the same closed-bar
    # period. The +1 minute keeps the inclusive 1m row count inside seven days.
    end = end - timedelta(minutes=1)
    start = end - DEMO_YFINANCE_1M_LIMIT + timedelta(minutes=1)
    return _format_cli_datetime(start), _format_cli_datetime(end)


def apply_demo_window(args: argparse.Namespace) -> argparse.Namespace:
    """Mutate parsed args so demo mode always fits Yahoo's 1m retention window."""
    args.start_date, args.end_date = resolve_demo_window(args.end_date)
    return args


def selected_sources_for_args(args: argparse.Namespace) -> tuple[str, ...]:
    """Resolve source execution order from parsed repo-level CLI arguments."""
    if args.demo:
        return DEMO_SOURCE_ORDER
    sources = selected_sources(args.sources)
    if (
        args.allow_free_fresh_tail
        and "multiasset" not in sources
        and "yfinance" not in sources
    ):
        sources = tuple(
            source for source in SOURCE_ORDER if source in {*sources, "yfinance"}
        )
    return sources


def _run_step(name: str, cmd: list[str], cwd: Path) -> bool:
    print("\n" + "=" * 70)
    print(name)
    print("=" * 70)
    print("Command:", " ".join(cmd))
    sys.stdout.flush()
    result = subprocess.run(cmd, cwd=str(cwd), check=False)
    return result.returncode == 0


def build_bybit_cmd(args: argparse.Namespace) -> tuple[list[str], Path]:
    """Build the child command that updates 24/7 crypto data from Bybit."""
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
    """Build the explicit Twelve Data fallback command for spot-style assets."""
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
    """Build the explicit Databento-only futures backfill/update command."""
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
    """Build the production non-crypto router command."""
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
    """Build the Yahoo Finance command for demo or validated recent-tail updates."""
    if args.demo:
        cmd = [
            sys.executable,
            "update_data.py",
            "--demo",
            "--htf-only",
            "--start-date",
            args.start_date,
            "--end-date",
            args.end_date,
        ]
    else:
        cmd = [
            sys.executable,
            "update_data.py",
            "--providers",
            "yfinance",
            "--core",
            "--htf-only",
            "--start-date",
            args.start_date,
            "--end-date",
            args.end_date,
        ]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.estimate_only:
        cmd.append("--estimate-only")
    return cmd, PROJECT_ROOT / "fetchingMultiAsset"


def build_status_cmd(source: str) -> tuple[list[str], Path]:
    """Build a no-write status command for one configured source group."""
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


def build_derive_ohlcv_cmd(args: argparse.Namespace) -> tuple[list[str], Path]:
    """Build the local canonical OHLCV derivation command."""
    cmd = [
        sys.executable,
        "scripts/feature_engineering/materialize_canonical_ohlcv.py",
        "--assets",
        args.canonical_assets,
        "--timeframes",
        args.derived_ohlcv_timeframes,
    ]
    if args.status:
        cmd.append("--status")
    if args.dry_run:
        cmd.append("--dry-run")
    return cmd, PROJECT_ROOT


def build_refresh_canonical_cmd(args: argparse.Namespace) -> tuple[list[str], Path]:
    """Build the local canonical OHLCV refresh command."""
    cmd = [
        sys.executable,
        "scripts/feature_engineering/materialize_canonical_ohlcv.py",
        "--assets",
        args.canonical_assets,
        "--refresh-1m-from-raw",
        "--timeframes",
        args.derived_ohlcv_timeframes,
        "--start-date",
        args.canonical_start_date,
    ]
    canonical_end_date = args.canonical_end_date or args.end_date
    if canonical_end_date:
        cmd.extend(["--end-date", canonical_end_date])
    return cmd, PROJECT_ROOT


def should_refresh_canonical(args: argparse.Namespace) -> bool:
    """Return whether this update run should refresh canonical OHLCV."""
    return (
        bool(args.core)
        and not args.status
        and not args.dry_run
        and not args.estimate_only
        and not args.skip_canonical_refresh
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the repo-root data update CLI parser."""
    parser = argparse.ArgumentParser(
        description="Core data update orchestrator: Bybit -> multi-asset auto source",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python update_data.py --demo
  python update_data.py --demo --dry-run
  python update_data.py --core
  python update_data.py --core --dry-run
  python update_data.py --core --estimate-only
  python update_data.py --core --sources multiasset --dry-run
  python update_data.py --core --sources databento --estimate-only
  python update_data.py --core --sources yfinance --dry-run
  python update_data.py --core --sources twelvedata --start-date 2024-01-01 --end-date 2024-02-01
  python update_data.py --core --status
  python update_data.py --core --skip-canonical-refresh  # raw source update only
  python update_data.py --live-1m --once                 # one forward-paper poll
  python update_data.py --live-start                     # start background service
  python update_data.py --live-status                    # inspect feed/paper health
  python update_data.py --live-stop                      # orderly SIGTERM
        """,
    )
    parser.add_argument(
        "--core",
        action="store_true",
        help="Run the intended core source mix in fixed order.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help=(
            "Free-source demo mode. Fetch the latest Yahoo 1m retention window "
            "for all core assets using Bybit crypto plus Yahoo Finance futures "
            "proxies only; Databento, Twelve Data, and other paid sources are not used."
        ),
    )
    parser.add_argument(
        "--live-1m",
        action="store_true",
        help=(
            "Run the finalized-1m first-seen journal and forward paper service "
            "in the foreground. No real orders are supported."
        ),
    )
    parser.add_argument(
        "--live-start",
        action="store_true",
        help="Start the finalized-1m forward paper service in the background.",
    )
    parser.add_argument(
        "--live-stop",
        action="store_true",
        help="Stop the verified background forward paper process with SIGTERM.",
    )
    parser.add_argument(
        "--live-status",
        action="store_true",
        help="Print background process, provider-grade, and paper-cohort status.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="With --live-1m, fetch and journal one bounded provider pass, then exit.",
    )
    parser.add_argument(
        "--live-child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--live-assets",
        default=DEFAULT_LIVE_ASSETS,
        help="Forward-paper assets: core or a comma-separated canonical subset.",
    )
    parser.add_argument(
        "--live-timeframes",
        default=DEFAULT_LIVE_TIMEFRAMES,
        help="Comma-separated canonical paper timeframes; default is all seven.",
    )
    parser.add_argument(
        "--live-poll-seconds",
        type=float,
        default=60.0,
        help="Polling interval. The 60-second default aligns to minute close plus 5s.",
    )
    parser.add_argument(
        "--live-state-dir",
        default="",
        help=(
            "Optional runtime directory. Default is RISKYIELDMM_STATE_DIR or "
            "$XDG_STATE_HOME/riskyieldmm/forward_paper."
        ),
    )
    parser.add_argument(
        "--live-strategy-manifest",
        default="",
        help=(
            "Optional digest-verified JSON strategy manifest or accepted optimizer "
            "response. The frozen strategy becomes part of a new immutable paper cohort."
        ),
    )
    parser.add_argument(
        "--live-fee-bps",
        type=float,
        default=1.0,
        help="Normalized paper fee in basis points per fill.",
    )
    parser.add_argument(
        "--live-slippage-bps",
        type=float,
        default=1.0,
        help="Normalized paper slippage in basis points per fill.",
    )
    parser.add_argument(
        "--live-spread-bps",
        type=float,
        default=0.0,
        help=(
            "Full bid/ask spread scenario in basis points. The normalized bar "
            "simulator charges half on each execution side; default 0 because "
            "historical quotes are unavailable."
        ),
    )
    parser.add_argument(
        "--live-execution-latency-minutes",
        type=int,
        default=1,
        help=(
            "Additional whole-minute paper latency after actual first observation; "
            "default 1."
        ),
    )
    parser.add_argument(
        "--require-live-feeds",
        action="store_true",
        help=(
            "Fail instead of using delayed Yahoo futures fallbacks. With current "
            "adapters this limits the service to BTCUSDT/ETHUSDT."
        ),
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
        "--derive-ohlcv-timeframes",
        action="store_true",
        help=(
            "Compatibility/manual mode: after source update/status, derive canonical "
            "15m,1h,4h,8h,12h,1d OHLCV bars from local canonical 1m files. "
            "Normal --core write runs already refresh canonical OHLCV unless skipped."
        ),
    )
    parser.add_argument(
        "--derived-ohlcv-timeframes",
        default=DEFAULT_DERIVED_CANONICAL_TIMEFRAMES,
        help="Comma-separated derived canonical OHLCV timeframes; 24h aliases to 1d.",
    )
    parser.add_argument(
        "--skip-canonical-refresh",
        action="store_true",
        help=(
            "Do not refresh canonical OHLCV after source writes. Use for raw-only "
            "maintenance runs."
        ),
    )
    parser.add_argument(
        "--canonical-assets",
        default=DEFAULT_CANONICAL_ASSETS,
        help="Canonical refresh asset set: core or comma-separated HTF asset ids.",
    )
    parser.add_argument(
        "--canonical-start-date",
        default=DEFAULT_START_DATE,
        help=(
            "Start date for canonical 1m refresh from raw files. Empty/none disables "
            "the lower bound."
        ),
    )
    parser.add_argument(
        "--canonical-end-date",
        default="",
        help="Optional exclusive end date for canonical 1m refresh from raw files.",
    )
    parser.add_argument(
        "--htf-only",
        action="store_true",
        help=(
            "Compatibility flag for the repo-root orchestrator. Core multi-asset "
            "updates already target the HTF source contract."
        ),
    )
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


def _live_imports() -> dict[str, object]:
    """Import the Analyst runtime only for explicit live/paper commands."""

    analyst_path = str(ANALYST_ROOT)
    if analyst_path not in sys.path:
        sys.path.insert(0, analyst_path)
    from chart_config import CANONICAL_TIMEFRAMES, CORE_ASSETS
    from forward_paper.runtime import (
        atomic_write_json,
        default_state_dir,
        iso_utc,
        read_json_object,
        utc_now,
    )
    from forward_paper.service import ForwardPaperConfig, ForwardPaperCoordinator
    from forward_paper.supervisor import (
        inspect_process,
        log_path,
        remove_own_pid_file,
        start_background,
        status_path,
        stop_background,
    )
    from minute_replay import IndicatorStrategyConfig, ReplayCostConfig

    return {
        "CANONICAL_TIMEFRAMES": CANONICAL_TIMEFRAMES,
        "CORE_ASSETS": CORE_ASSETS,
        "ForwardPaperConfig": ForwardPaperConfig,
        "ForwardPaperCoordinator": ForwardPaperCoordinator,
        "IndicatorStrategyConfig": IndicatorStrategyConfig,
        "ReplayCostConfig": ReplayCostConfig,
        "atomic_write_json": atomic_write_json,
        "default_state_dir": default_state_dir,
        "inspect_process": inspect_process,
        "iso_utc": iso_utc,
        "log_path": log_path,
        "read_json_object": read_json_object,
        "remove_own_pid_file": remove_own_pid_file,
        "start_background": start_background,
        "status_path": status_path,
        "stop_background": stop_background,
        "utc_now": utc_now,
    }


def _resolved_live_state_dir(args: argparse.Namespace, live: dict[str, object]) -> Path:
    if args.live_state_dir:
        return Path(args.live_state_dir).expanduser().resolve()
    return live["default_state_dir"]()  # type: ignore[operator]


def _resolved_live_assets(
    raw: str,
    *,
    known_assets: tuple[str, ...],
) -> tuple[str, ...]:
    if raw.strip().lower() == "core":
        return known_assets
    values = tuple(
        dict.fromkeys(part.strip().upper() for part in raw.split(",") if part.strip())
    )
    unknown = [asset for asset in values if asset not in known_assets]
    if not values or unknown:
        known = ", ".join(known_assets)
        raise ValueError(
            f"Unknown or empty --live-assets selection {unknown!r}. Known: {known}"
        )
    return values


def _resolved_live_timeframes(
    raw: str,
    *,
    known_timeframes: tuple[str, ...],
) -> tuple[str, ...]:
    values = tuple(
        dict.fromkeys(part.strip().lower() for part in raw.split(",") if part.strip())
    )
    unknown = [value for value in values if value not in known_timeframes]
    if not values or unknown:
        known = ", ".join(known_timeframes)
        raise ValueError(
            f"Unknown or empty --live-timeframes selection {unknown!r}. Known: {known}"
        )
    return values


def _live_strategy_from_manifest(
    raw_path: str,
    *,
    live: dict[str, object],
) -> object:
    """Load one frozen strategy without silently accepting a rejected optimizer run."""

    strategy_type = live["IndicatorStrategyConfig"]
    if not raw_path:
        return strategy_type()  # type: ignore[operator]
    path = Path(raw_path).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read live strategy manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Live strategy manifest must be a JSON object")

    if "best_config" in payload:
        status = payload.get("status")
        if status != "accepted_for_paper_trading":
            raise ValueError(
                "Optimizer strategy manifest is not accepted_for_paper_trading"
            )
        raw_strategy = payload.get("best_config")
        expected_config_hash = payload.get("best_config_hash")
        if not isinstance(raw_strategy, dict) or not isinstance(
            expected_config_hash, str
        ):
            raise ValueError("Optimizer strategy manifest is incomplete")
        encoded = json.dumps(
            raw_strategy,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        actual_config_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        if actual_config_hash != expected_config_hash:
            raise ValueError("Optimizer best_config_hash does not match best_config")
    else:
        raw_strategy = payload.get("strategy")
        if not isinstance(raw_strategy, dict):
            raise ValueError(
                "Live strategy manifest needs strategy or accepted best_config"
            )
        if not isinstance(payload.get("strategy_digest"), str):
            raise ValueError("Frozen strategy manifest requires a strategy_digest")

    values = dict(raw_strategy)
    values.pop("horizon_template", None)
    if isinstance(values.get("horizons"), list):
        values["horizons"] = tuple(values["horizons"])
    try:
        strategy = strategy_type(**values)  # type: ignore[operator]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Live strategy manifest is invalid: {exc}") from exc
    expected_digest = payload.get("strategy_digest")
    if expected_digest is not None and expected_digest != strategy.digest():
        raise ValueError("Live strategy_digest does not match strategy")
    return strategy


def _live_research_status_from_manifest(raw_path: str) -> str:
    """Keep explicitly frozen but unaccepted strategies in observe-only mode."""

    if not raw_path:
        return "historical_optimizer_rejected_observe_only"
    path = Path(raw_path).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read live strategy manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Live strategy manifest must be a JSON object")
    if payload.get("status") == "accepted_for_paper_trading" and isinstance(
        payload.get("best_config"), dict
    ):
        return "optimizer_accepted_forward_validation"
    return "frozen_strategy_observe_only"


def _build_live_config(args: argparse.Namespace, live: dict[str, object]) -> object:
    assets = _resolved_live_assets(
        args.live_assets,
        known_assets=tuple(live["CORE_ASSETS"]),  # type: ignore[arg-type]
    )
    timeframes = _resolved_live_timeframes(
        args.live_timeframes,
        known_timeframes=tuple(live["CANONICAL_TIMEFRAMES"]),  # type: ignore[arg-type]
    )
    costs = live["ReplayCostConfig"](  # type: ignore[operator]
        fee_bps=args.live_fee_bps,
        spread_bps=args.live_spread_bps,
        slippage_bps=args.live_slippage_bps,
        execution_latency_minutes=args.live_execution_latency_minutes,
    )
    return live["ForwardPaperConfig"](  # type: ignore[operator]
        assets=assets,
        timeframes=timeframes,
        strategy=_live_strategy_from_manifest(
            args.live_strategy_manifest,
            live=live,
        ),
        costs=costs,
        state_dir=_resolved_live_state_dir(args, live),
        poll_interval_seconds=args.live_poll_seconds,
        require_live_feeds=args.require_live_feeds,
        research_status=_live_research_status_from_manifest(
            args.live_strategy_manifest
        ),
    )


def build_live_child_cmd(args: argparse.Namespace) -> list[str]:
    """Build the exact foreground command supervised by --live-start."""

    cmd = [
        sys.executable,
        "-u",
        str((PROJECT_ROOT / "update_data.py").resolve()),
        "--live-1m",
        "--live-child",
        "--live-assets",
        args.live_assets,
        "--live-timeframes",
        args.live_timeframes,
        "--live-poll-seconds",
        str(args.live_poll_seconds),
        "--live-fee-bps",
        str(args.live_fee_bps),
        "--live-slippage-bps",
        str(args.live_slippage_bps),
        "--live-spread-bps",
        str(args.live_spread_bps),
        "--live-execution-latency-minutes",
        str(args.live_execution_latency_minutes),
    ]
    if args.live_state_dir:
        cmd.extend(["--live-state-dir", args.live_state_dir])
    if args.live_strategy_manifest:
        cmd.extend(["--live-strategy-manifest", args.live_strategy_manifest])
    if args.require_live_feeds:
        cmd.append("--require-live-feeds")
    return cmd


def _print_live_status(
    *,
    state_dir: Path,
    live: dict[str, object],
) -> int:
    process = live["inspect_process"](state_dir)  # type: ignore[operator]
    try:
        payload = live["read_json_object"](  # type: ignore[operator]
            live["status_path"](state_dir)  # type: ignore[operator]
        )
    except (OSError, ValueError) as exc:
        payload = {"status": "invalid_status_file", "error": str(exc)}
    print("FORWARD PAPER SERVICE")
    print(f"Process: {'RUNNING' if process.running else 'STOPPED'} ({process.reason})")
    if process.pid is not None:
        print(f"PID: {process.pid}")
    print(f"State: {state_dir}")
    print(f"Log: {live['log_path'](state_dir)}")  # type: ignore[operator]
    if not payload:
        print("Status: not started")
        return 0
    print(f"Heartbeat status: {payload.get('status', 'unknown')}")
    print(f"Heartbeat: {payload.get('heartbeat_at', '-')}")
    print(f"Research gate: {payload.get('research_status', '-')}")
    print("Real order routing: DISABLED")
    feeds = payload.get("feeds")
    if isinstance(feeds, dict):
        print("Feeds:")
        for asset, feed in feeds.items():
            if not isinstance(feed, dict):
                continue
            print(
                f"  {asset:<8} {str(feed.get('provider', '-')):<10} "
                f"{str(feed.get('quality', '-')):<7} "
                f"{str(feed.get('status', '-')):<26} "
                f"through={feed.get('last_source_timestamp', '-')}"
            )
    print("JSON:")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _run_live_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    live = _live_imports()
    state_dir = _resolved_live_state_dir(args, live)
    if args.live_status:
        return _print_live_status(state_dir=state_dir, live=live)
    if args.live_stop:
        result = live["stop_background"](state_dir)  # type: ignore[operator]
        print(f"Forward paper service: {result.reason}")
        return 0 if not result.running else 1
    if args.live_start:
        # Validate the full cohort before detaching a child that would fail
        # opaquely in a log file.
        _build_live_config(args, live)
        command = build_live_child_cmd(args)
        result = live["start_background"](  # type: ignore[operator]
            command=command,
            state_dir=state_dir,
            cwd=PROJECT_ROOT,
            identity_tokens=(
                str((PROJECT_ROOT / "update_data.py").resolve()),
                "--live-child",
            ),
        )
        print(f"Forward paper service: {result.reason}")
        if result.pid is not None:
            print(f"PID: {result.pid}")
        print(f"Log: {live['log_path'](state_dir)}")  # type: ignore[operator]
        return 0 if result.running else 1

    if not args.live_1m:
        parser.error("A live service mode was not selected")
    config = _build_live_config(args, live)
    stop_event = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    previous_handlers: dict[int, object] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, request_stop)

    print("FORWARD PAPER 1M SERVICE")
    print(f"Assets: {', '.join(config.assets)}")
    print(f"Timeframes: {', '.join(config.timeframes)}")
    print(f"State: {config.state_dir}")
    print("Real order routing: DISABLED")
    print("Profitability guarantee: NONE")
    coordinator = None
    try:
        coordinator = live["ForwardPaperCoordinator"](config)  # type: ignore[operator]
        if args.once:
            status = coordinator.poll_once()
            print(json.dumps(status, indent=2, sort_keys=True))
        else:
            coordinator.run_forever(stop_event)
    except Exception as exc:
        error_payload = {
            "schema_version": 1,
            "status": "error",
            "pid": os.getpid(),
            "heartbeat_at": live["iso_utc"](live["utc_now"]()),  # type: ignore[operator]
            "error": f"{exc.__class__.__name__}: {exc}",
            "real_order_routing": False,
            "profitability_guaranteed": False,
        }
        live["atomic_write_json"](  # type: ignore[operator]
            live["status_path"](state_dir),  # type: ignore[operator]
            error_payload,
        )
        print(error_payload["error"], file=sys.stderr)
        return 1
    finally:
        if coordinator is not None:
            coordinator.close()
        if args.live_child:
            live["remove_own_pid_file"](state_dir, pid=os.getpid())  # type: ignore[operator]
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the selected data update sources in deterministic order."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    live_mode_count = sum(
        bool(value)
        for value in (
            args.live_1m,
            args.live_start,
            args.live_stop,
            args.live_status,
        )
    )
    mode_count = int(bool(args.core)) + int(bool(args.demo)) + live_mode_count
    if mode_count == 0:
        parser.error(
            "Use --core, --demo, --live-1m, --live-start, --live-stop, or "
            "--live-status. Broad --all orchestration is intentionally unsupported."
        )
    if mode_count > 1:
        parser.error("Select exactly one core, demo, or live service mode.")
    if args.once and not args.live_1m:
        parser.error("--once is valid only with --live-1m.")
    if args.live_child and not args.live_1m:
        parser.error("--live-child is an internal --live-1m flag.")
    if live_mode_count:
        try:
            return _run_live_command(args, parser)
        except ValueError as exc:
            parser.error(str(exc))
    if args.demo and args.sources:
        parser.error("--demo chooses sources automatically; do not pass --sources.")
    if args.demo:
        apply_demo_window(args)

    sources = selected_sources_for_args(args)
    started_at = datetime.now(timezone.utc)
    print("\n" + "=" * 70)
    print("CORE DATA UPDATE ORCHESTRATOR")
    print("=" * 70)
    print(f"Started: {started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Period: {args.start_date} -> {args.end_date}")
    print(f"Sources: {', '.join(sources)}")
    print(
        "Canonical OHLCV refresh: "
        f"{'enabled' if should_refresh_canonical(args) else 'disabled'}"
    )
    if args.demo:
        print("Mode: DEMO/free sources only")
        print("Order: Bybit crypto -> Yahoo Finance futures proxies")
        print("Paid sources disabled: Databento, Twelve Data")
    else:
        print("Order: Bybit crypto -> multi-asset auto source")
    if "multiasset" in sources:
        print("Multi-asset auto: Yahoo recent-tail first, Databento fallback if needed")
    if "twelvedata" in sources:
        print("Twelve Data selected explicitly as fallback/manual source")
    if args.demo and "yfinance" in sources:
        print("Yahoo Finance selected as standalone demo source")
    elif "yfinance" in sources:
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
    if success and should_refresh_canonical(args):
        cmd, cwd = build_refresh_canonical_cmd(args)
        success = _run_step("REFRESH CANONICAL OHLCV", cmd, cwd) and success
    elif success and args.derive_ohlcv_timeframes:
        cmd, cwd = build_derive_ohlcv_cmd(args)
        success = _run_step("DERIVE CANONICAL OHLCV TIMEFRAMES", cmd, cwd) and success

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
