"""Controlled runner for L1-precompute + fast backtest.

Goal: make end-to-end validation runs reproducible and resumable.

Typical usage (all 20 configs, production-parity, common end bar):
    PYTHONPATH=. python scripts/target_models/validation/run_fast_validation.py \
        --backtest-rows 300 \
        --precompute ensure \
        --align-global-end \
        --fail-fast

Quick sanity run:
    PYTHONPATH=. python scripts/target_models/validation/run_fast_validation.py \
        --configs returns_1bar returns_12bar \
        --backtest-rows 3 \
        --precompute force \
        --precomputed-dir data/precomputed_tmp \
        --results-dir data/backtest_results_tmp
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import polars as pl

from scripts.target_models.validation.fast_backtest import (
    BacktestConfig,
    FastBacktester,
)
from scripts.target_models.validation.l1_precompute import (
    L1PrecomputeConfig,
    get_all_config_names,
    load_iteration_index,
    load_precomputed_metadata,
    precompute_l1_for_config,
)


def _utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _parse_config_name(config_name: str) -> tuple[str, int]:
    parts = config_name.rsplit("_", 1)
    if len(parts) != 2 or not parts[1].endswith("bar"):
        raise ValueError(f"Invalid config name: {config_name}")
    target = parts[0]
    horizon = int(parts[1].replace("bar", ""))
    return target, horizon


def _filtered_end_timestamp_and_last_idx(
    config_name: str,
    data_dir: Path,
    max_timestamp: pd.Timestamp | None = None,
) -> tuple[pd.Timestamp, int]:
    """Match production drop_na semantics (all features + y_target not-null)."""

    data_path = data_dir / f"{config_name}.parquet"
    df_pl = pl.read_parquet(data_path)

    if "timestamp" not in df_pl.columns:
        raise ValueError(f"No timestamp column in {config_name} data")

    y_cols = [c for c in df_pl.columns if c.startswith("y_")]
    feature_cols = [
        c for c in df_pl.columns if not c.startswith("y_") and c != "timestamp"
    ]

    target, _ = _parse_config_name(config_name)
    y_col = f"y_{target}"
    if y_col not in df_pl.columns:
        y_col = y_cols[0] if y_cols else None
    if y_col is None:
        raise ValueError(f"No target column found for {config_name}")

    not_null_exprs = [pl.col(c).is_not_null() for c in feature_cols]
    not_null_exprs.append(pl.col(y_col).is_not_null())
    df_pl = df_pl.filter(pl.all_horizontal(not_null_exprs))

    if max_timestamp is not None:
        df_pl = df_pl.filter(pl.col("timestamp") <= max_timestamp.to_pydatetime())

    ts = df_pl.select(["timestamp"]).to_pandas()["timestamp"]
    if len(ts) == 0:
        raise ValueError(f"No rows after drop_na filtering for {config_name}")

    last_idx = len(ts) - 1
    return pd.Timestamp(ts.iloc[last_idx]), int(last_idx)


def _resolve_configs(
    *,
    configs: list[str] | None,
    targets: list[str] | None,
    horizons: list[int] | None,
) -> list[str]:
    resolved = configs[:] if configs else get_all_config_names()

    if targets is not None:
        target_set = set(targets)
        resolved = [c for c in resolved if _parse_config_name(c)[0] in target_set]

    if horizons is not None:
        horizon_set = set(horizons)
        resolved = [c for c in resolved if _parse_config_name(c)[1] in horizon_set]

    # Preserve original ordering (important for reproducibility)
    all_order = {name: i for i, name in enumerate(get_all_config_names())}
    resolved.sort(key=lambda x: all_order.get(x, 10_000))
    return resolved


def _load_metadata_if_exists(
    config_name: str, l1_cfg: L1PrecomputeConfig
) -> dict | None:
    try:
        meta = load_precomputed_metadata(config_name, l1_cfg)
        return asdict(meta)
    except FileNotFoundError:
        return None


def _metadata_satisfies(
    *,
    metadata: dict,
    expected_backtest_rows: int,
    expected_l2_window_size: int,
    expected_horizon: int,
    require_drop_na: bool,
    expected_truncate_end_timestamp: str | None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if int(metadata.get("backtest_rows", -1)) != int(expected_backtest_rows):
        reasons.append(
            f"backtest_rows mismatch (have {metadata.get('backtest_rows')}, want {expected_backtest_rows})"
        )

    if int(metadata.get("l2_window_size", -1)) != int(expected_l2_window_size):
        reasons.append(
            f"l2_window_size mismatch (have {metadata.get('l2_window_size')}, want {expected_l2_window_size})"
        )

    # Expected: l2_pred_size == horizon
    if int(metadata.get("l2_pred_size", 1)) != int(expected_horizon):
        reasons.append(
            f"l2_pred_size mismatch (have {metadata.get('l2_pred_size')}, want {expected_horizon})"
        )

    if int(metadata.get("horizon", expected_horizon)) != int(expected_horizon):
        reasons.append(
            f"horizon mismatch (have {metadata.get('horizon')}, want {expected_horizon})"
        )

    if require_drop_na and metadata.get("data_drop_na") is not True:
        reasons.append("data_drop_na is not True")

    if expected_truncate_end_timestamp is not None:
        if metadata.get("truncate_end_timestamp") != expected_truncate_end_timestamp:
            reasons.append(
                "truncate_end_timestamp mismatch "
                f"(have {metadata.get('truncate_end_timestamp')}, want {expected_truncate_end_timestamp})"
            )

    return (len(reasons) == 0), reasons


def _verify_precompute_finishes_at_dataset_end(
    *,
    config_name: str,
    l1_cfg: L1PrecomputeConfig,
    max_timestamp: pd.Timestamp | None,
) -> dict:
    index = load_iteration_index(config_name, l1_cfg)
    if not index:
        raise ValueError(f"Empty index for {config_name}")

    last_entry = max(index, key=lambda x: x["iteration"])
    data_last_ts, data_last_idx = _filtered_end_timestamp_and_last_idx(
        config_name, l1_cfg.data_dir, max_timestamp=max_timestamp
    )

    aligned_pred_idx = int(last_entry.get("aligned_pred_idx", last_entry["pred_idx"]))
    aligned_ts = pd.Timestamp(
        last_entry.get("aligned_timestamp", last_entry["timestamp"])
    )

    ok_idx = aligned_pred_idx == data_last_idx
    ok_ts = aligned_ts == data_last_ts

    return {
        "config": config_name,
        "ok": bool(ok_idx and ok_ts),
        "data_last_idx": int(data_last_idx),
        "aligned_pred_idx": int(aligned_pred_idx),
        "data_last_timestamp": pd.Timestamp(data_last_ts).isoformat(),
        "aligned_timestamp": pd.Timestamp(aligned_ts).isoformat(),
        "total_iterations": len(index),
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Run fast validation (optional L1 precompute + L2-only fast backtests) with resumable outputs."
    )

    # Config selection
    p.add_argument("--configs", nargs="*", default=None, help="Explicit config names")
    p.add_argument(
        "--targets",
        nargs="*",
        default=None,
        help="Filter by targets (returns/direction/volatility/vol_regime/trend_regime)",
    )
    p.add_argument(
        "--horizons", nargs="*", type=int, default=None, help="Filter by horizons"
    )

    # Paths
    p.add_argument("--data-dir", type=Path, default=Path("data/datasets"))
    p.add_argument("--precomputed-dir", type=Path, default=Path("data/precomputed"))
    p.add_argument("--results-dir", type=Path, default=Path("data/backtest_results"))

    # Core run settings
    p.add_argument("--backtest-rows", type=int, default=300)
    p.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run folder name under results-dir (default: fast_validation_<timestamp>)",
    )

    # Precompute behavior
    p.add_argument(
        "--precompute",
        choices=["skip", "ensure", "force"],
        default="ensure",
        help="skip: require existing L1; ensure: build if missing/mismatched; force: rebuild all",
    )
    p.add_argument(
        "--align-global-end",
        action="store_true",
        default=True,
        help="Truncate all configs to a shared end timestamp (default: enabled)",
    )
    p.add_argument(
        "--no-align-global-end",
        dest="align_global_end",
        action="store_false",
        help="Disable truncation; each config ends at its own dataset end",
    )
    p.add_argument(
        "--global-end-timestamp",
        type=str,
        default=None,
        help="Override shared end timestamp (ISO8601). If omitted and align-global-end is enabled, uses earliest end across configs.",
    )

    # Backtest behavior
    p.add_argument("--no-conformal", action="store_true")
    p.add_argument("--fail-fast", action="store_true")
    p.add_argument("--continue-on-error", action="store_true")
    p.add_argument(
        "--resume",
        action="store_true",
        help="Skip configs already present in summary.json",
    )
    p.add_argument("--no-verify-ends", action="store_true")
    p.add_argument("--write-csv", action="store_true")

    args = p.parse_args(argv)

    configs = _resolve_configs(
        configs=args.configs, targets=args.targets, horizons=args.horizons
    )
    if not configs:
        raise SystemExit("No configs selected")

    run_id = args.run_id or f"fast_validation_{_utc_now_compact()}"
    run_dir = args.results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_json = run_dir / "summary.json"
    summary_csv = run_dir / "summary.csv"

    # Compute global end timestamp (if requested)
    global_end: pd.Timestamp | None = None
    if args.align_global_end:
        if args.global_end_timestamp is not None:
            global_end = pd.Timestamp(args.global_end_timestamp)
        else:
            ends = [
                _filtered_end_timestamp_and_last_idx(name, args.data_dir)[0]
                for name in configs
            ]
            global_end = min(ends)

    expected_truncate_end_timestamp = (
        global_end.isoformat() if global_end is not None else None
    )

    # Load resume state
    existing_done: set[str] = set()
    existing_rows: list[dict] = []
    if args.resume and summary_json.exists():
        with open(summary_json) as f:
            payload = json.load(f)
        for row in payload.get("results", []):
            cfg_name = row.get("config")
            if cfg_name:
                existing_done.add(cfg_name)
                existing_rows.append(row)

    l1_cfg = L1PrecomputeConfig(
        data_dir=args.data_dir,
        output_dir=args.precomputed_dir,
        backtest_rows=args.backtest_rows,
    )

    bt_cfg = BacktestConfig(
        data_dir=args.data_dir,
        precomputed_dir=args.precomputed_dir,
        output_dir=run_dir,
        backtest_rows=args.backtest_rows,
        conformal_enabled=not args.no_conformal,
    )
    backtester = FastBacktester(config=bt_cfg)

    started = time.time()
    results: list[dict] = list(existing_rows)

    print(f"Run: {run_id}")
    print(f"Configs: {len(configs)}")
    print(f"Data dir: {args.data_dir}")
    print(f"Precomputed dir: {args.precomputed_dir}")
    print(f"Results dir: {run_dir}")
    print(f"Backtest rows: {args.backtest_rows}")
    print(f"Precompute: {args.precompute}")
    print(f"Align global end: {bool(args.align_global_end)}")
    if global_end is not None:
        print(f"Global end timestamp: {global_end.isoformat()}")

    for i, config_name in enumerate(configs, start=1):
        if config_name in existing_done:
            print(f"[{i}/{len(configs)}] {config_name} [RESUME: skip]")
            continue

        target, horizon = _parse_config_name(config_name)

        try:
            # Precompute management
            meta_dict = _load_metadata_if_exists(config_name, l1_cfg)

            need_precompute = False
            mismatch_reasons: list[str] = []

            if args.precompute == "force":
                need_precompute = True
            elif args.precompute == "skip":
                if meta_dict is None:
                    raise FileNotFoundError(
                        f"Missing precompute metadata for {config_name}"
                    )
            else:  # ensure
                if meta_dict is None:
                    need_precompute = True
                else:
                    ok, mismatch_reasons = _metadata_satisfies(
                        metadata=meta_dict,
                        expected_backtest_rows=args.backtest_rows,
                        expected_l2_window_size=bt_cfg.l2_window_size,
                        expected_horizon=horizon,
                        require_drop_na=True,
                        expected_truncate_end_timestamp=expected_truncate_end_timestamp,
                    )
                    need_precompute = not ok

            if need_precompute:
                reason_str = (
                    "; ".join(mismatch_reasons) if mismatch_reasons else "missing"
                )
                print(f"[{i}/{len(configs)}] {config_name} [PRECOMPUTE: {reason_str}]")
                precompute_l1_for_config(
                    config_name,
                    cfg=l1_cfg,
                    verbose=True,
                    force=True,
                    max_timestamp=global_end,
                )
                meta_dict = _load_metadata_if_exists(config_name, l1_cfg)
            else:
                print(f"[{i}/{len(configs)}] {config_name} [PRECOMPUTE: ok]")

            if meta_dict is None:
                raise RuntimeError(
                    f"Failed to load metadata after precompute for {config_name}"
                )

            # Optional end verification
            end_check = None
            if not args.no_verify_ends:
                end_check = _verify_precompute_finishes_at_dataset_end(
                    config_name=config_name, l1_cfg=l1_cfg, max_timestamp=global_end
                )
                if not end_check["ok"]:
                    raise RuntimeError(
                        f"End alignment failed: {json.dumps(end_check, indent=2)}"
                    )

            # Backtest
            t0 = time.time()
            bt_res = backtester.run(config_name, verbose=False)
            elapsed = time.time() - t0

            row = {
                "config": config_name,
                "target": target,
                "horizon": horizon,
                "task_type": bt_res.task_type,
                "n_iterations": bt_res.n_iterations,
                "elapsed_sec": round(elapsed, 2),
                "coverage": bt_res.coverage,
                **dict(bt_res.metrics),
                "precompute_metadata": meta_dict,
            }
            if end_check is not None:
                row["end_alignment"] = end_check

            results.append(row)
            print(
                f"    backtest ok: iters={bt_res.n_iterations} elapsed={elapsed:.1f}s coverage={bt_res.coverage}"
            )

            # Write incremental summary for continuity
            payload = {
                "run_id": run_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "data_dir": str(args.data_dir),
                "precomputed_dir": str(args.precomputed_dir),
                "backtest_rows": int(args.backtest_rows),
                "align_global_end": bool(args.align_global_end),
                "global_end_timestamp": global_end.isoformat()
                if global_end is not None
                else None,
                "results": results,
            }
            with open(summary_json, "w") as f:
                json.dump(payload, f, indent=2, default=str)

        except Exception as e:
            err_row = {
                "config": config_name,
                "error": str(e),
            }
            results.append(err_row)
            print(f"    ERROR: {e}")

            payload = {
                "run_id": run_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "data_dir": str(args.data_dir),
                "precomputed_dir": str(args.precomputed_dir),
                "backtest_rows": int(args.backtest_rows),
                "align_global_end": bool(args.align_global_end),
                "global_end_timestamp": global_end.isoformat()
                if global_end is not None
                else None,
                "results": results,
            }
            with open(summary_json, "w") as f:
                json.dump(payload, f, indent=2, default=str)

            if args.fail_fast and not args.continue_on_error:
                raise

    total_dt = time.time() - started

    if args.write_csv:
        flat_rows = []
        for r in results:
            if "error" in r:
                continue
            # Keep the CSV shallow (avoid embedding huge metadata dicts)
            flat_rows.append(
                {
                    k: v
                    for k, v in r.items()
                    if k
                    not in {
                        "precompute_metadata",
                    }
                    and not k.startswith("end_alignment")
                }
            )
        if flat_rows:
            pd.DataFrame(flat_rows).to_csv(summary_csv, index=False)

    ok = sum(1 for r in results if "error" not in r)
    failed = sum(1 for r in results if "error" in r)

    print(f"\nDONE: {ok} ok, {failed} failed, {total_dt / 60:.1f} minutes")
    print(f"Summary: {summary_json}")
    if args.write_csv:
        print(f"CSV: {summary_csv}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
