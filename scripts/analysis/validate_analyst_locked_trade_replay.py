#!/usr/bin/env python3
"""Run the locked Analyst strategy over a common causal replay window.

This is a diagnostic of the current execution path, not an optimizer.  The
strategy and cost assumptions are declared once below and are never selected
using evaluation results.  Every target-timeframe decision is built from
finalized real one-minute rows and filled by ``minute_replay`` at the first real
one-minute open at or after the shared paper/replay eligibility timestamp.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYST_ROOT = PROJECT_ROOT / "Risk_Yield_Meta_Model_Analyst_0_0_1"
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from chart_config import CANONICAL_TIMEFRAMES, CORE_ASSETS  # noqa: E402
from minute_replay import (  # noqa: E402
    INGESTION_SAFETY_LAG_SECONDS,
    IndicatorStrategyConfig,
    ReplayCostConfig,
    load_canonical_minute_window,
    run_minute_replay,
)

PROTOCOL_VERSION = "analyst_locked_matrix_v1"
DEFAULT_END = datetime(2026, 7, 10, 21, 0, tzinfo=timezone.utc)
DEFAULT_DAYS = 180
LOCKED_STRATEGY = IndicatorStrategyConfig()
LOCKED_COSTS = ReplayCostConfig(
    fee_bps=1.0,
    slippage_bps=1.0,
    spread_bps=0.0,
    execution_latency_minutes=1,
)


@dataclass(frozen=True)
class DescriptiveGates:
    minimum_fills: int = 20
    maximum_drawdown_pct: float = 20.0
    minimum_net_return_pct: float = 0.0
    minimum_annualized_sharpe: float = 0.0
    stressed_one_way_cost_bps: float = 4.0


GATES = DescriptiveGates()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_datetime(raw: str) -> datetime:
    return _utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))


def _finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def selection_gates(metrics: dict[str, Any]) -> dict[str, bool]:
    """Return predeclared descriptive checks for one locked evaluation."""

    net_return = _finite(metrics.get("total_return_pct"))
    sharpe = _finite(metrics.get("annualized_sharpe"))
    drawdown = _finite(metrics.get("max_drawdown_pct"))
    breakeven = _finite(metrics.get("breakeven_all_in_cost_bps"))
    fills = int(metrics.get("fill_count") or 0)
    return {
        "minimum_fills": fills >= GATES.minimum_fills,
        "net_return_positive": net_return is not None
        and net_return > GATES.minimum_net_return_pct,
        "annualized_sharpe_positive": sharpe is not None
        and sharpe > GATES.minimum_annualized_sharpe,
        "drawdown_at_most_20pct": drawdown is not None
        and drawdown <= GATES.maximum_drawdown_pct,
        "gross_edge_exceeds_2x_cost_scenario": breakeven is not None
        and breakeven > GATES.stressed_one_way_cost_bps,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "ok"]
    positive = [
        row
        for row in completed
        if bool(row.get("gates", {}).get("net_return_positive"))
    ]
    all_gates = [
        row for row in completed if row.get("gates") and all(row["gates"].values())
    ]
    returns = [
        float(row["metrics"]["total_return_pct"])
        for row in completed
        if _finite(row.get("metrics", {}).get("total_return_pct")) is not None
    ]
    sharpes = [
        float(row["metrics"]["annualized_sharpe"])
        for row in completed
        if _finite(row.get("metrics", {}).get("annualized_sharpe")) is not None
    ]
    return {
        "selection_count": len(rows),
        "completed_count": len(completed),
        "failure_count": len(rows) - len(completed),
        "positive_net_return_count": len(positive),
        "positive_net_return_rate": (
            None if not completed else len(positive) / len(completed)
        ),
        "all_descriptive_gates_count": len(all_gates),
        "all_descriptive_gates_rate": (
            None if not completed else len(all_gates) / len(completed)
        ),
        "median_net_return_pct": None if not returns else median(returns),
        "median_annualized_sharpe": None if not sharpes else median(sharpes),
        "total_fills": sum(
            int(row.get("metrics", {}).get("fill_count") or 0) for row in completed
        ),
        "total_round_trips": sum(
            int(row.get("metrics", {}).get("round_trip_count") or 0)
            for row in completed
        ),
        "total_excluded_synthetic_minutes": sum(
            int(row.get("data_quality", {}).get("excluded_synthetic_minutes") or 0)
            for row in completed
        ),
        "total_suppressed_incomplete_target_bars": sum(
            int(
                row.get("data_quality", {}).get("suppressed_incomplete_target_bars")
                or 0
            )
            for row in completed
        ),
    }


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def run_matrix(
    *,
    assets: Iterable[str],
    timeframes: Iterable[str],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    assets = tuple(str(value).strip().upper() for value in assets)
    timeframes = tuple(str(value).strip().lower() for value in timeframes)
    strategy = LOCKED_STRATEGY.as_dict()
    costs = LOCKED_COSTS.as_dict()
    protocol = {
        "protocol_version": PROTOCOL_VERSION,
        "evaluation_start": _iso(start),
        "replay_clock": _iso(end),
        "assets": list(assets),
        "timeframes": list(timeframes),
        "strategy": strategy,
        "strategy_digest": LOCKED_STRATEGY.digest(),
        "costs": costs,
        "cost_digest": LOCKED_COSTS.digest(),
        "historical_observation_lag_seconds": INGESTION_SAFETY_LAG_SECONDS,
        "fill_rule": "first_real_1m_open_at_or_after_eligibility",
        "synthetic_policy": "excluded_from_signal_input_and_fill_eligibility",
        "optimization": "none_locked_before_evaluation",
        "gates": asdict(GATES),
        "gate_role": "descriptive_not_parameter_selection",
    }
    protocol["protocol_digest"] = _digest(protocol)
    rows: list[dict[str, Any]] = []
    for asset in assets:
        for timeframe in timeframes:
            started = time.perf_counter()
            print(f"START {asset} {timeframe}", flush=True)
            row: dict[str, Any] = {"asset": asset, "timeframe": timeframe}
            try:
                frame, source = load_canonical_minute_window(
                    asset=asset,
                    timeframe=timeframe,
                    start=start,
                    end=end,
                    now=end + timedelta(seconds=INGESTION_SAFETY_LAG_SECONDS),
                )
                result = run_minute_replay(
                    frame,
                    asset=asset,
                    timeframe=timeframe,
                    strategy=LOCKED_STRATEGY,
                    costs=LOCKED_COSTS,
                    evaluation_start=start,
                    replay_clock=end,
                    event_limit=0,
                    capture_series=False,
                )
                metadata = result["metadata"]
                metrics = result["metrics"]
                row.update(
                    {
                        "status": "ok",
                        "source": {
                            "source_generation": source["source_generation"],
                            "source_snapshot": source["source_snapshot"],
                            "loaded_start": source["loaded_start"],
                            "loaded_end": source["loaded_end"],
                            "source_rows": source["source_rows"],
                        },
                        "metrics": metrics,
                        "gates": selection_gates(metrics),
                        "data_quality": {
                            name: metadata[name]
                            for name in (
                                "input_source_rows",
                                "processed_real_source_minutes",
                                "excluded_synthetic_minutes",
                                "invalid_source_rows",
                                "continuous_source_gap_count",
                                "missing_continuous_source_minutes",
                                "target_closed_bars",
                                "target_complete_bars",
                                "suppressed_incomplete_target_bars",
                                "target_bar_completeness_counts",
                            )
                        }
                        | {
                            "order_cancelled_data_gap_count": metrics[
                                "order_cancelled_data_gap_count"
                            ]
                        },
                    }
                )
            except Exception as exc:
                row.update(
                    {
                        "status": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            row["elapsed_seconds"] = time.perf_counter() - started
            rows.append(row)
            summary = row.get("metrics", {})
            print(
                "DONE "
                f"{asset} {timeframe} status={row['status']} "
                f"return={summary.get('total_return_pct')} "
                f"sharpe={summary.get('annualized_sharpe')} "
                f"fills={summary.get('fill_count')} "
                f"seconds={row['elapsed_seconds']:.2f}",
                flush=True,
            )
    return {
        "schema_version": 1,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "research_only": True,
        "profitability_guaranteed": False,
        "as_was_live": False,
        "protocol": protocol,
        "aggregate": aggregate(rows),
        "selections": rows,
        "limitations": [
            "Current canonical revisions have no historical first-seen or revision timestamps.",
            "The strategy executes CUSUM and online trend/volatility logic; Market Context v1 chart diagnostics are not execution gates.",
            "Normalized PnL omits instrument multipliers, rolls, funding, borrow, FX conversion, margin, liquidation and market impact.",
            "OHLCV next-open fills do not model quote depth, queue position, partial fills or venue order lifecycle.",
            "The fixed generic cost scenario is not an instrument-specific historical cost series.",
            "Each selection is an independent normalized stream, not a capital-netted portfolio.",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--end", type=_parse_datetime, default=DEFAULT_END)
    parser.add_argument("--assets", nargs="+", default=list(CORE_ASSETS))
    parser.add_argument("--timeframes", nargs="+", default=list(CANONICAL_TIMEFRAMES))
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            PROJECT_ROOT
            / "docs/validation/meta_model_analyst_locked_trade_replay_2026-07-12.json"
        ),
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.days <= 0:
        raise SystemExit("--days must be positive")
    end = _utc(args.end)
    start = end - timedelta(days=args.days)
    result = run_matrix(
        assets=args.assets,
        timeframes=args.timeframes,
        start=start,
        end=end,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result["aggregate"], indent=2), flush=True)
    print(f"WROTE {args.output}", flush=True)


if __name__ == "__main__":
    main()
