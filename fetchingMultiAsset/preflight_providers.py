#!/usr/bin/env python3
"""Safe provider readiness checks before full multi-asset backfills."""

from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime, timedelta, timezone

try:
    from .asset_config import ASSETS, DATABENTO_FUTURES
    from .fetch_databento import configured_databento_api_key, estimate_costs
    from .fetch_twelve_data import (
        TwelveDataClient,
        configured_api_key,
        load_local_secret_files,
        twelve_values_to_ohlcv,
    )
except ImportError:  # pragma: no cover - script execution from fetchingMultiAsset/
    from asset_config import ASSETS, DATABENTO_FUTURES  # type: ignore
    from fetch_databento import (  # type: ignore
        configured_databento_api_key,
        estimate_costs,
    )
    from fetch_twelve_data import (  # type: ignore
        TwelveDataClient,
        configured_api_key,
        load_local_secret_files,
        twelve_values_to_ohlcv,
    )


def _print_key_status() -> None:
    load_local_secret_files()
    print("KEY STATUS")
    print("-" * 70)
    print("TWELVE_DATA_API_KEY:", "present" if configured_api_key() else "missing")
    print(
        "DATABENTO_API_KEY:",
        "present" if configured_databento_api_key() else "missing",
    )
    print(
        "databento SDK:",
        "installed" if importlib.util.find_spec("databento") else "missing",
    )


def _check_twelve_symbols() -> bool:
    key = configured_api_key()
    if not key:
        print("Twelve Data: SKIP (missing key)")
        return False
    client = TwelveDataClient(key)
    print("\nTWELVE DATA SYMBOL CHECK")
    print("-" * 70)
    ok = True
    for asset in ASSETS:
        try:
            payload = client.symbol_search(asset.provider_symbol)
            matches = payload.get("data") or []
            print(
                f"{asset.symbol:<7} {asset.provider_symbol:<10} matches={len(matches)}"
            )
            if not matches:
                ok = False
        except Exception as exc:
            ok = False
            print(f"{asset.symbol:<7} ERROR {exc}")
    return ok


def _check_twelve_sample() -> bool:
    key = configured_api_key()
    if not key:
        return False
    client = TwelveDataClient(key)
    end = datetime.now(timezone.utc) - timedelta(days=1)
    start = end - timedelta(hours=2)
    print("\nTWELVE DATA SAMPLE CHECK")
    print("-" * 70)
    try:
        values = client.time_series(
            symbol="EUR/USD",
            interval="15min",
            start=start,
            end=end,
            outputsize=16,
        )
        df = twelve_values_to_ohlcv(values, "15m")
        print(f"EURUSD 15m sample rows={df.height}, columns={df.columns}")
        return df.height > 0
    except Exception as exc:
        print(f"EURUSD 15m sample ERROR {exc}")
        return False


def _check_databento_cost(start: str, end: str) -> bool:
    if not configured_databento_api_key():
        print("Databento: SKIP (missing key)")
        return False
    if not importlib.util.find_spec("databento"):
        print("Databento: SDK missing. Install with: python -m pip install databento")
        return False

    print("\nDATABENTO COST CHECK")
    print("-" * 70)
    try:
        estimates = estimate_costs(assets=DATABENTO_FUTURES, start=start, end=end)
    except Exception as exc:
        print(f"Databento cost estimate ERROR {exc}")
        return False

    total = 0.0
    for item in estimates:
        total += item.cost_usd
        print(
            f"{item.asset:<3} {item.provider_symbol:<8} "
            f"{item.dataset:<9} {item.schema:<8} cost=${item.cost_usd:.8f}"
        )
    print(f"total estimated Databento cost: ${total:.8f}")
    return True


def main(argv: list[str] | None = None) -> int:
    """Run safe credential, symbol, sample, and cost checks for providers."""
    parser = argparse.ArgumentParser(
        description="Safe readiness checks for Twelve Data and Databento providers",
    )
    parser.add_argument("--skip-twelve-live", action="store_true")
    parser.add_argument("--skip-databento-cost", action="store_true")
    parser.add_argument("--databento-start", default="2024-01-02T14:30:00Z")
    parser.add_argument("--databento-end", default="2024-01-02T15:30:00Z")
    args = parser.parse_args(argv)

    _print_key_status()
    twelve_ok = True
    if not args.skip_twelve_live:
        twelve_ok = _check_twelve_symbols() and _check_twelve_sample()

    databento_ok = True
    if not args.skip_databento_cost:
        databento_ok = _check_databento_cost(args.databento_start, args.databento_end)

    print("\nPREFLIGHT RESULT")
    print("-" * 70)
    print("Twelve Data:", "OK" if twelve_ok else "CHECK NEEDED")
    print("Databento:", "OK" if databento_ok else "CHECK NEEDED")
    return 0 if twelve_ok and databento_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
