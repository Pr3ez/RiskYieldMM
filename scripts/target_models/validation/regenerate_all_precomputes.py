from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import polars as pl

from scripts.target_models.validation.l1_precompute import (
    L1PrecomputeConfig,
    get_all_config_names,
    load_iteration_index,
    precompute_l1_for_config,
)


def _filtered_end_timestamp_and_last_idx(
    config_name: str,
    cfg: L1PrecomputeConfig,
    max_timestamp: pd.Timestamp | None = None,
) -> tuple[pd.Timestamp, int]:
    data_path = cfg.data_dir / f"{config_name}.parquet"
    df_pl = pl.read_parquet(data_path)

    if "timestamp" not in df_pl.columns:
        raise ValueError(f"No timestamp column in {config_name} data")

    y_cols = [c for c in df_pl.columns if c.startswith("y_")]
    feature_cols = [
        c for c in df_pl.columns if not c.startswith("y_") and c != "timestamp"
    ]

    target = config_name.rsplit("_", 1)[0]
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

    df = df_pl.select(["timestamp"]).to_pandas()
    timestamps = df["timestamp"]
    if len(timestamps) == 0:
        raise ValueError(f"No rows after drop_na filtering for {config_name}")

    last_idx = len(timestamps) - 1
    last_ts = timestamps.iloc[last_idx]
    return pd.Timestamp(last_ts), last_idx


def verify_config_finishes_at_dataset_end(
    config_name: str,
    cfg: L1PrecomputeConfig,
    max_timestamp: pd.Timestamp | None = None,
) -> dict:
    index = load_iteration_index(config_name, cfg)
    if not index:
        raise ValueError(f"Empty index for {config_name}")

    last_entry = max(index, key=lambda x: x["iteration"])
    data_last_ts, data_last_idx = _filtered_end_timestamp_and_last_idx(
        config_name, cfg, max_timestamp=max_timestamp
    )

    aligned_pred_idx = int(last_entry["aligned_pred_idx"])
    aligned_ts = pd.Timestamp(last_entry["aligned_timestamp"])

    ok_idx = aligned_pred_idx == data_last_idx
    ok_ts = aligned_ts == data_last_ts

    return {
        "config": config_name,
        "ok": bool(ok_idx and ok_ts),
        "data_last_idx": data_last_idx,
        "aligned_pred_idx": aligned_pred_idx,
        "data_last_timestamp": data_last_ts.isoformat(),
        "aligned_timestamp": aligned_ts.isoformat(),
        "total_iterations": len(index),
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Regenerate all L1 precomputes (production-parity) and verify alignment."
    )
    p.add_argument("--backtest-rows", type=int, default=300)
    p.add_argument("--output-dir", type=Path, default=Path("data/precomputed"))
    p.add_argument("--data-dir", type=Path, default=Path("data/datasets"))
    p.add_argument(
        "--force",
        action="store_true",
        help="Delete existing per-config precompute dirs first",
    )
    p.add_argument(
        "--configs",
        nargs="*",
        default=None,
        help="Optional subset of config names to run (default: all 20)",
    )
    p.add_argument(
        "--max-configs",
        type=int,
        default=None,
        help="Optional cap for number of configs (useful for quick sanity runs)",
    )
    p.add_argument(
        "--allow-different-ends",
        action="store_true",
        help="Do not fail if different configs have different dataset end timestamps",
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
        help="Override the shared end timestamp (ISO8601). If not set and --align-global-end is enabled, uses the earliest end across configs.",
    )
    p.add_argument("--no-verify", action="store_true")
    p.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Where to write summary JSON (default: <output-dir>/precompute_summary.json)",
    )
    args = p.parse_args(argv)

    cfg = L1PrecomputeConfig(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        backtest_rows=args.backtest_rows,
    )

    configs = args.configs or get_all_config_names()
    if args.max_configs is not None:
        configs = configs[: args.max_configs]

    global_end: pd.Timestamp | None = None
    if args.align_global_end:
        if args.global_end_timestamp is not None:
            global_end = pd.Timestamp(args.global_end_timestamp)
        else:
            ends = [
                _filtered_end_timestamp_and_last_idx(name, cfg)[0] for name in configs
            ]
            global_end = min(ends)

    results: list[dict] = []
    end_timestamps: dict[str, str] = {}

    print(f"Regenerating {len(configs)} configs with backtest_rows={cfg.backtest_rows}")
    print(f"Data dir: {cfg.data_dir}")
    print(f"Output dir: {cfg.output_dir}")
    print(f"Force: {args.force}")
    print(f"Align global end: {args.align_global_end}")
    if global_end is not None:
        print(f"Global end timestamp: {global_end.isoformat()}")

    total_t0 = time.time()
    for i, config_name in enumerate(configs, start=1):
        print(f"\n[{i}/{len(configs)}] {config_name}")
        t0 = time.time()
        meta = precompute_l1_for_config(
            config_name,
            cfg=cfg,
            verbose=True,
            force=args.force,
            max_timestamp=global_end,
        )
        dt = time.time() - t0

        meta_dict = asdict(meta)
        meta_dict["elapsed_sec"] = round(dt, 2)

        if meta.total_iterations != cfg.backtest_rows:
            raise RuntimeError(
                f"{config_name}: produced {meta.total_iterations} iterations, expected {cfg.backtest_rows}."
            )

        if not args.no_verify:
            check = verify_config_finishes_at_dataset_end(
                config_name, cfg, max_timestamp=global_end
            )
            meta_dict["end_alignment"] = check
            if not check["ok"]:
                raise RuntimeError(
                    f"End alignment failed: {json.dumps(check, indent=2)}"
                )
            end_timestamps[config_name] = check["data_last_timestamp"]

        results.append(meta_dict)

    total_dt = time.time() - total_t0

    if not args.no_verify:
        unique_ends = sorted(set(end_timestamps.values()))
        print(f"\nUnique dataset-end timestamps across configs: {len(unique_ends)}")
        for ts in unique_ends[:10]:
            print(f"  - {ts}")
        if len(unique_ends) != 1 and not args.allow_different_ends:
            raise RuntimeError(
                f"Expected a single common dataset-end timestamp across configs, got {len(unique_ends)}. "
                f"Re-run with --allow-different-ends to bypass."
            )

    summary_path = args.summary_json or (cfg.output_dir / "precompute_summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(
            {
                "backtest_rows": cfg.backtest_rows,
                "output_dir": str(cfg.output_dir),
                "data_dir": str(cfg.data_dir),
                "force": bool(args.force),
                "total_elapsed_sec": round(total_dt, 2),
                "configs": results,
            },
            f,
            indent=2,
        )

    print(f"\nDONE in {total_dt / 60:.1f} minutes")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
