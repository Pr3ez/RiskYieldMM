#!/usr/bin/env python3
"""Validate Market Context chart overlays across all canonical selections."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYST_ROOT = PROJECT_ROOT / "Risk_Yield_Meta_Model_Analyst_0_0_1"
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from chart_config import CANONICAL_SOURCE, build_chart_manifest  # noqa: E402
from chart_export import (  # noqa: E402
    INDICATOR_COMPARABLE_VOLATILITY,
    INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
    INDICATOR_PRIOR_STRUCTURE,
    build_lightweight_charts_payload,
    load_ohlcv_window_with_context,
    required_indicator_warmup_bars,
)
from market_context import MARKET_CONTEXT_VERSION  # noqa: E402

MARKET_CONTEXT_INDICATORS = (
    INDICATOR_PRIOR_STRUCTURE,
    INDICATOR_COMPARABLE_VOLATILITY,
    INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
)


def _canonical_selections() -> list[tuple[str, str]]:
    manifest = build_chart_manifest()
    return [
        (str(asset_entry["asset"]), str(timeframe_entry["timeframe"]))
        for asset_entry in manifest["assets"]
        for source_entry in asset_entry["sources"]
        if source_entry["source"] == CANONICAL_SOURCE
        for timeframe_entry in source_entry["timeframes"]
    ]


def _validate_points(
    *,
    asset: str,
    timeframe: str,
    name: str,
    points: list[dict[str, Any]],
    minimum: float | None = None,
    maximum: float | None = None,
) -> list[str]:
    prefix = f"{asset} {timeframe}: {name}"
    if not points:
        return [f"{prefix} is empty"]
    failures: list[str] = []
    for point in points:
        value = point.get("value")
        if value is None or not math.isfinite(float(value)):
            failures.append(f"{prefix} contains a non-finite value")
            break
        typed = float(value)
        if minimum is not None and typed < minimum:
            failures.append(f"{prefix} is below {minimum:g}")
            break
        if maximum is not None and typed > maximum:
            failures.append(f"{prefix} is above {maximum:g}")
            break
    return failures


def validate_market_context_matrix(*, visible_bars: int = 256) -> dict[str, Any]:
    """Build and validate all 56 canonical asset/timeframe chart selections."""

    if visible_bars <= 0:
        raise ValueError("visible_bars must be positive")
    started = time.perf_counter()
    failures: list[str] = []
    status_counts: Counter[str] = Counter()
    point_totals: Counter[str] = Counter()
    timings: list[dict[str, Any]] = []
    selections = _canonical_selections()

    for asset, timeframe in selections:
        selection_started = time.perf_counter()
        hidden_requested = required_indicator_warmup_bars(
            MARKET_CONTEXT_INDICATORS,
            timeframe=timeframe,
        )
        try:
            frame, metadata, context = load_ohlcv_window_with_context(
                asset=asset,
                timeframe=timeframe,
                source=CANONICAL_SOURCE,
                max_bars=visible_bars,
                indicator_warmup_bars=hidden_requested,
            )
            payload = build_lightweight_charts_payload(
                frame,
                metadata,
                indicators=MARKET_CONTEXT_INDICATORS,
                indicator_context=context,
            )
            structure = payload["overlays"][INDICATOR_PRIOR_STRUCTURE]
            volatility = payload["overlays"][INDICATOR_COMPARABLE_VOLATILITY]
            participation = payload["overlays"][INDICATOR_PHASE_ADJUSTED_PARTICIPATION]
            statuses = (
                str(structure.get("status")),
                str(volatility.get("status")),
                str(participation.get("status")),
            )
            status_counts[" / ".join(statuses)] += 1

            series = {
                "prior_structure_48_upper": structure["channels"]["48"]["upper"],
                "volatility_percentile": volatility["volatility_percentile"],
                "volatility_fast_slow_score": volatility["fast_slow_ratio_score"],
                "volatility_range_shock_score": volatility["range_shock_score"],
                "participation_rvol_score": participation["rvol_score"],
            }
            failures.extend(
                _validate_points(
                    asset=asset,
                    timeframe=timeframe,
                    name="prior_structure_48_upper",
                    points=series["prior_structure_48_upper"],
                    minimum=0.0,
                )
            )
            failures.extend(
                _validate_points(
                    asset=asset,
                    timeframe=timeframe,
                    name="volatility_percentile",
                    points=series["volatility_percentile"],
                    minimum=0.0,
                    maximum=1.0,
                )
            )
            for name in (
                "volatility_fast_slow_score",
                "volatility_range_shock_score",
                "participation_rvol_score",
            ):
                failures.extend(
                    _validate_points(
                        asset=asset,
                        timeframe=timeframe,
                        name=name,
                        points=series[name],
                        minimum=-1.0,
                        maximum=1.0,
                    )
                )
            candle_times = {int(row["time"]) for row in payload["candles"]}
            if any(
                int(point["time"]) not in candle_times
                for point in series["prior_structure_48_upper"]
            ):
                failures.append(
                    f"{asset} {timeframe}: source-stamped structure channel "
                    "does not align with visible candles"
                )
            for family, overlay in (
                ("structure", structure),
                ("volatility", volatility),
                ("participation", participation),
            ):
                last = overlay.get("last") or {}
                if not all(
                    last.get(key) for key in ("quality", "source_as_of", "as_of")
                ):
                    failures.append(
                        f"{asset} {timeframe}: {family} lacks last quality/timing"
                    )
                provenance = overlay.get("data_provenance") or {}
                if provenance.get("chart_source") != CANONICAL_SOURCE:
                    failures.append(
                        f"{asset} {timeframe}: {family} lacks canonical provenance"
                    )
            for name, points in series.items():
                point_totals[name] += len(points)
            timings.append(
                {
                    "asset": asset,
                    "timeframe": timeframe,
                    "seconds": time.perf_counter() - selection_started,
                    "hidden_requested": hidden_requested,
                    "hidden_loaded": context.height,
                    "statuses": list(statuses),
                }
            )
        except Exception as exc:
            failures.append(f"{asset} {timeframe}: {exc.__class__.__name__}: {exc}")

    timings.sort(key=lambda item: float(item["seconds"]), reverse=True)
    return {
        "schema_version": "analyst_market_context_matrix_validation_v1",
        "market_context_version": MARKET_CONTEXT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": CANONICAL_SOURCE,
        "visible_bars_per_selection": visible_bars,
        "selection_count": len(selections),
        "expected_selection_count": 56,
        "passed": not failures and len(selections) == 56,
        "failure_count": len(failures),
        "failures": failures,
        "point_totals": dict(sorted(point_totals.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "elapsed_seconds": time.perf_counter() - started,
        "slowest_selections": timings[:10],
        "contracts": {
            "structure_channels": "strictly_prior_source_stamped",
            "post_close_series": "next_action_timestamp",
            "volatility_percentile_range": [0.0, 1.0],
            "signed_score_range": [-1.0, 1.0],
            "diagnostic_only": True,
            "changes_execution_decisions": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visible-bars", type=int, default=256)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = validate_market_context_matrix(visible_bars=args.visible_bars)
    encoded = json.dumps(result, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{encoded}\n", encoding="utf-8")
    print(encoded)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
