"""
HTF Feature Engineering Module
==============================
Computes features for ANY timeframe for HTF backtest.

Adaptive design:
- Auto-detects available data sources in fetchingByBit directory
- Automatically finds best source for each data type (native TF or higher)
- Aligns higher TF data to lower TF rows using source availability metadata
- Supports any timeframe: 1m, 5m, 15m, 1h, 4h, 8h, etc.

Usage:
    from scripts.feature_engineering.compute_htf_features import (
        HTFFeatureEngine,
        load_and_compute_htf_features,
    )

    # Option 1: Use convenience function
    df = load_and_compute_htf_features(
        data_dir=Path("fetchingByBit"),
        timeframe="5m",
        save_path=Path("data/htf_features_5m.parquet")
    )

    # Option 2: Use engine for more control
    engine = HTFFeatureEngine(data_dir=Path("fetchingByBit"))
    engine.discover_available_sources()
    df_raw = engine.load_data_for_timeframe("5m")
    df_features = engine.compute_features(df_raw, "5m")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import numba
except ImportError:  # pragma: no cover - allows lightweight runtime verification
    class _NumbaFallback:
        @staticmethod
        def njit(*args, **kwargs):
            if args and callable(args[0]) and len(args) == 1 and not kwargs:
                return args[0]

            def decorator(func):
                return func

            return decorator

    numba = _NumbaFallback()

# =============================================================================
# TIMEFRAME UTILITIES
# =============================================================================

# Ordered from smallest to largest
TIMEFRAME_ORDER = ["1m", "5m", "15m", "30m", "1h", "4h", "8h", "1d"]

TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "8h": 480,
    "1d": 1440,
}


def parse_timeframe(tf: str) -> int:
    """Convert timeframe string to minutes."""
    if tf in TIMEFRAME_MINUTES:
        return TIMEFRAME_MINUTES[tf]
    # Try parsing custom format
    match = re.match(r"(\d+)(m|h|d)", tf.lower())
    if match:
        num, unit = int(match.group(1)), match.group(2)
        if unit == "m":
            return num
        elif unit == "h":
            return num * 60
        elif unit == "d":
            return num * 1440
    raise ValueError(f"Unknown timeframe: {tf}")


def get_higher_timeframes(tf: str) -> list[str]:
    """Get all timeframes higher than the given one."""
    tf_mins = parse_timeframe(tf)
    return [t for t in TIMEFRAME_ORDER if parse_timeframe(t) > tf_mins]


def get_lower_or_equal_timeframes(tf: str) -> list[str]:
    """Get all timeframes lower than or equal to the given one."""
    tf_mins = parse_timeframe(tf)
    return [t for t in TIMEFRAME_ORDER if parse_timeframe(t) <= tf_mins]


TIMESTAMP_ROLES = {
    "bar_start",
    "available_at",
    "settlement_at",
    "period_start_aggregate",
}


def _resolve_offset_minutes(
    offset: str | int | float | None,
    source_tf: str,
) -> float:
    if offset is None:
        return 0.0
    if isinstance(offset, (int, float)):
        return float(offset)

    resolved = str(offset).strip().lower()
    if resolved in {"", "none"}:
        return 0.0
    if resolved == "source_tf":
        return float(parse_timeframe(source_tf))
    return float(parse_timeframe(resolved))


def _default_availability_offset(timestamp_role: str, source_tf: str) -> float:
    if timestamp_role in {"bar_start", "period_start_aggregate"}:
        return float(parse_timeframe(source_tf))
    return 0.0


def _normalize_timestamp_for_merge(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series)
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    return ts.astype("datetime64[ns]")


def source_available_timestamps(
    timestamps: pd.Series,
    *,
    source_tf: str,
    timestamp_role: str,
    availability_offset: str | int | float | None = None,
    publication_lag: str | int | float | None = None,
) -> pd.Series:
    """Return source timestamps shifted to when their values are usable."""
    if timestamp_role not in TIMESTAMP_ROLES:
        raise ValueError(
            f"Unknown timestamp_role={timestamp_role!r}; "
            f"expected one of {sorted(TIMESTAMP_ROLES)}"
        )

    ts = _normalize_timestamp_for_merge(timestamps)
    offset_minutes = (
        _default_availability_offset(timestamp_role, source_tf)
        if availability_offset is None
        else _resolve_offset_minutes(availability_offset, source_tf)
    )
    lag_minutes = _resolve_offset_minutes(publication_lag, source_tf)
    return ts + pd.to_timedelta(offset_minutes + lag_minutes, unit="m")


# =============================================================================
# DATA SOURCE TYPES
# =============================================================================

# Map data type to directory pattern and expected columns
# NOTE: Actual file naming conventions discovered from fetchingByBit directory:
#   - OHLCV:
#       * 1m-4h: batch files "btcusdt_linear_sorted_batch_*.parquet" in sorted-{tf}-bybit-linear/
#       * 8h: single file "btcusdt_8h.parquet" in sorted-8h-bybit-linear/
#       * 1d: batch files in sorted-1d-bybit-linear/
#   - Mark price:
#       * Most TFs: "btcusdt_mark.parquet"
#       * 8h: "btcusdt_mark_price_8h.parquet"
#   - Index price: similar pattern to mark
#   - Premium price: similar pattern
#   - Open interest:
#       * Most TFs: "btcusdt_oi.parquet"
#       * 8h: "btcusdt_open_interest_8h.parquet"
#   - LS ratio: "btcusdt_ls_ratio.parquet" (consistent)
#   - Funding: "btcusdt_funding_rate.parquet" in funding-rate-bybit-linear/ (no TF suffix)
#
# Strategy: Try multiple file patterns and use the first one that exists
DATA_SOURCE_PATTERNS = {
    "ohlcv": {
        "dir_pattern": "sorted-{tf}-bybit-linear",
        "file_patterns": [
            "btcusdt_linear_sorted_batch_*.parquet",  # Batch files (1m-4h, 1d)
            "btcusdt_{tf}.parquet",  # Single file with TF (8h)
        ],
        "columns": ["timestamp", "open", "high", "low", "close", "volume"],
        "rename": {},
        "timestamp_role": "bar_start",
        "availability_offset": "source_tf",
        "publication_lag": "0m",
    },
    "mark_price": {
        "dir_pattern": "mark-price-{tf}-bybit-linear",
        "file_patterns": [
            "btcusdt_mark.parquet",  # Most TFs
            "btcusdt_mark_price_{tf}.parquet",  # 8h
        ],
        "columns": ["timestamp", "open", "high", "low", "close"],
        "rename": {
            "open": "markOpen",
            "high": "markHigh",
            "low": "markLow",
            "close": "markClose",
        },
        "timestamp_role": "bar_start",
        "availability_offset": "source_tf",
        "publication_lag": "0m",
    },
    "index_price": {
        "dir_pattern": "index-price-{tf}-bybit-linear",
        "file_patterns": [
            "btcusdt_index.parquet",  # Most TFs
            "btcusdt_index_price_{tf}.parquet",  # 8h
        ],
        "columns": ["timestamp", "open", "high", "low", "close"],
        "rename": {
            "open": "indexOpen",
            "high": "indexHigh",
            "low": "indexLow",
            "close": "indexClose",
        },
        "timestamp_role": "bar_start",
        "availability_offset": "source_tf",
        "publication_lag": "0m",
    },
    "premium_price": {
        "dir_pattern": "premium-price-{tf}-bybit-linear",
        "file_patterns": [
            "btcusdt_premium.parquet",  # Most TFs
            "btcusdt_premium_price_{tf}.parquet",  # 8h
        ],
        "columns": ["timestamp", "open", "high", "low", "close"],
        "rename": {
            "open": "premiumOpen",
            "high": "premiumHigh",
            "low": "premiumLow",
            "close": "premiumClose",
        },
        "timestamp_role": "bar_start",
        "availability_offset": "source_tf",
        "publication_lag": "0m",
    },
    "open_interest": {
        "dir_pattern": "open-interest-{tf}-bybit-linear",
        "file_patterns": [
            "btcusdt_oi.parquet",  # Most TFs
            "btcusdt_open_interest_{tf}.parquet",  # 8h
        ],
        "columns": ["timestamp", "openInterest"],
        "rename": {},
        "timestamp_role": "available_at",
        "availability_offset": "0m",
        "publication_lag": "0m",
    },
    "long_short_ratio": {
        "dir_pattern": "long-short-ratio-{tf}-bybit-linear",
        "file_patterns": ["btcusdt_ls_ratio.parquet"],  # Consistent naming
        "columns": ["timestamp", "buyRatio", "sellRatio"],
        "rename": {},
        "derived": {"longShortRatio": lambda df: df["buyRatio"] / df["sellRatio"]},
        "timestamp_role": "available_at",
        "availability_offset": "0m",
        "publication_lag": "0m",
    },
    "funding_rate": {
        "dir_pattern": "funding-rate-bybit-linear",
        "file_patterns": ["btcusdt_funding_rate.parquet"],
        "columns": ["timestamp", "fundingRate"],
        "rename": {},
        "is_fixed_tf": True,  # No timeframe in directory name
        "native_tf": "8h",
        "timestamp_role": "settlement_at",
        "availability_offset": "0m",
        "publication_lag": "0m",
    },
}


@dataclass
class DataSourceInfo:
    """Information about an available data source."""

    data_type: str
    available_tfs: list[str]
    dir_path: Path | None = None

    def get_best_tf_for(self, target_tf: str) -> str | None:
        """
        Get the best available TF for the target timeframe.
        Prefers native TF, falls back to lowest higher TF.
        """
        if not self.available_tfs:
            return None

        target_mins = parse_timeframe(target_tf)

        # Check if native TF available
        if target_tf in self.available_tfs:
            return target_tf

        # Find lowest TF >= target (can broadcast down)
        higher_tfs = [
            tf for tf in self.available_tfs if parse_timeframe(tf) >= target_mins
        ]
        if higher_tfs:
            # Return the smallest one that's still >= target
            return min(higher_tfs, key=parse_timeframe)

        return None


# =============================================================================
# FEATURE ENGINE
# =============================================================================


@dataclass
class HTFFeatureEngine:
    """
    Adaptive HTF Feature Engine.

    Auto-discovers available data sources and computes features for any timeframe.
    """

    data_dir: Path
    sources: dict[str, DataSourceInfo] = field(default_factory=dict)
    verbose: bool = True

    def log(self, msg: str) -> None:
        """Print message if verbose."""
        if self.verbose:
            print(msg)

    def _find_files_for_source(
        self,
        config: dict,
        dir_path: Path,
        tf: str,
    ) -> tuple[list[Path], str]:
        """
        Find files matching any of the patterns for a data source.

        Returns:
            Tuple of (list of matched files, pattern that matched)
        """
        for pattern in config["file_patterns"]:
            pattern_formatted = pattern.format(tf=tf)

            if "*" in pattern_formatted:
                # Glob pattern (batch files)
                matched = sorted(dir_path.glob(pattern_formatted))
                if matched:
                    return matched, pattern_formatted
            else:
                # Single file
                file_path = dir_path / pattern_formatted
                if file_path.exists():
                    return [file_path], pattern_formatted

        return [], ""

    def discover_available_sources(self) -> dict[str, DataSourceInfo]:
        """
        Scan data directory and discover all available data sources.

        Returns:
            Dict mapping data_type -> DataSourceInfo
        """
        self.log(f"\n{'=' * 70}")
        self.log("DISCOVERING AVAILABLE DATA SOURCES")
        self.log(f"{'=' * 70}")
        self.log(f"Scanning: {self.data_dir}")

        self.sources = {}

        for data_type, config in DATA_SOURCE_PATTERNS.items():
            available_tfs = []

            if config.get("is_fixed_tf"):
                # Fixed TF source (e.g., funding rate)
                dir_path = self.data_dir / config["dir_pattern"]
                files, _ = self._find_files_for_source(
                    config, dir_path, config["native_tf"]
                )
                if files:
                    available_tfs = [config["native_tf"]]
                    self.sources[data_type] = DataSourceInfo(
                        data_type=data_type,
                        available_tfs=available_tfs,
                        dir_path=dir_path,
                    )
                    self.log(f"  ✓ {data_type}: {available_tfs}")
            else:
                # Variable TF source - scan for all available timeframes
                for tf in TIMEFRAME_ORDER:
                    dir_name = config["dir_pattern"].format(tf=tf)
                    dir_path = self.data_dir / dir_name

                    if not dir_path.exists():
                        continue

                    files, _ = self._find_files_for_source(config, dir_path, tf)
                    if files:
                        available_tfs.append(tf)

                if available_tfs:
                    self.sources[data_type] = DataSourceInfo(
                        data_type=data_type,
                        available_tfs=available_tfs,
                    )
                    self.log(f"  ✓ {data_type}: {available_tfs}")
                else:
                    self.log(f"  ✗ {data_type}: NOT FOUND")

        return self.sources

    def get_source_resolution_plan(
        self, target_tf: str
    ) -> dict[str, dict[str, Any]]:
        """
        Get a plan for how each data source will be resolved for target TF.

        Returns:
            Dict mapping data_type -> {source_tf, method}
        """
        if not self.sources:
            self.discover_available_sources()

        plan = {}

        for data_type, source_info in self.sources.items():
            best_tf = source_info.get_best_tf_for(target_tf)
            if best_tf:
                if best_tf == target_tf:
                    method = "native"
                else:
                    method = "broadcast"
                source_config = DATA_SOURCE_PATTERNS[data_type]
                plan[data_type] = {
                    "source_tf": best_tf,
                    "method": method,
                    "timestamp_role": source_config.get("timestamp_role"),
                    "availability_offset": source_config.get("availability_offset"),
                    "publication_lag": source_config.get("publication_lag"),
                }
            else:
                plan[data_type] = {"source_tf": None, "method": "unavailable"}

        return plan

    def load_single_source(
        self,
        data_type: str,
        tf: str,
    ) -> pd.DataFrame | None:
        """Load a single data source for given timeframe."""
        config = DATA_SOURCE_PATTERNS[data_type]

        # Get directory path
        if config.get("is_fixed_tf"):
            dir_path = self.data_dir / config["dir_pattern"]
        else:
            dir_name = config["dir_pattern"].format(tf=tf)
            dir_path = self.data_dir / dir_name

        if not dir_path.exists():
            return None

        # Find matching files using the new pattern system
        files, matched_pattern = self._find_files_for_source(config, dir_path, tf)
        if not files:
            return None

        # Load based on whether we have single or multiple files
        if len(files) == 1 and "*" not in matched_pattern:
            # Single file
            df = pd.read_parquet(files[0])
        else:
            # Multiple batch files - concat
            dfs = []
            for f in files:
                try:
                    dfs.append(pd.read_parquet(f))
                except Exception as e:
                    self.log(f"    Warning: Failed to load {f.name}: {e}")
            if not dfs:
                return None

            df = pd.concat(dfs, ignore_index=True)
            # Remove duplicates and sort
            df = (
                df.drop_duplicates(subset=["timestamp"])
                .sort_values("timestamp")
                .reset_index(drop=True)
            )

        # Filter to only expected columns (avoid extra columns like timestamp_ms causing merge issues)
        expected_cols = ["timestamp"] + config.get("columns", [])[
            1:
        ]  # timestamp + data cols
        extra_cols = [c for c in df.columns if c not in expected_cols]
        if extra_cols:
            df = df.drop(
                columns=[c for c in extra_cols if c in df.columns], errors="ignore"
            )

        # Apply renames
        if config.get("rename"):
            rename_cols = {k: v for k, v in config["rename"].items() if k in df.columns}
            df = df.rename(columns=rename_cols)

        # Apply derived columns
        if config.get("derived"):
            for col_name, func in config["derived"].items():
                df[col_name] = func(df)

        if "longShortRatio" in df.columns:
            ratio = df["longShortRatio"].replace([np.inf, -np.inf], np.nan)
            # A buy/sell ratio must stay strictly positive. Zero or negative
            # values are treated as missing source points and repaired later via
            # causal forward-fill on the aligned HTF frame.
            df["longShortRatio"] = ratio.mask(ratio <= 0, np.nan)

        return df

    def get_source_paths_for_timeframe(
        self,
        target_tf: str,
        *,
        extra_sources: list[str] | None = None,
    ) -> list[Path]:
        """
        Return the concrete source files used to augment features for `target_tf`.

        This lets downstream stages fingerprint the true fetched-source inputs
        instead of only the already-combined OHLCV parquet.
        """
        plan = self.get_source_resolution_plan(target_tf)
        source_names = extra_sources or [
            "mark_price",
            "index_price",
            "premium_price",
            "open_interest",
            "long_short_ratio",
            "funding_rate",
        ]

        resolved_paths: list[Path] = []
        for data_type in source_names:
            source_plan = plan.get(data_type, {})
            source_tf = source_plan.get("source_tf")
            if source_tf is None:
                continue

            config = DATA_SOURCE_PATTERNS[data_type]
            if config.get("is_fixed_tf"):
                dir_path = self.data_dir / config["dir_pattern"]
            else:
                dir_path = self.data_dir / config["dir_pattern"].format(tf=source_tf)

            files, _ = self._find_files_for_source(config, dir_path, source_tf)
            resolved_paths.extend(files)

        return sorted({path.resolve() for path in resolved_paths}, key=lambda path: str(path))

    def estimate_feature_output_columns(
        self,
        target_tf: str,
        *,
        include_auxiliary_sources: bool = False,
        extra_sources: list[str] | None = None,
        include_ohlcv: bool = True,
        distance_windows: dict[str, int] | None = None,
    ) -> list[str]:
        """
        Estimate the current feature-output schema for `target_tf`.

        The resume logic uses this to detect code-driven schema changes such as
        adding new fetched-source features or new composites. It deliberately
        avoids reading the full production history and instead uses a small
        synthetic preview frame plus the currently available source-resolution
        plan.
        """
        windows = self.get_window_scaling(target_tf)
        n_rows = max(32, windows["xlong"] + 4)
        freq = f"{parse_timeframe(target_tf)}min"
        timestamps = pd.date_range(
            "2000-01-01 00:00:00",
            periods=n_rows,
            freq=freq,
            tz="UTC",
        )
        close = pd.Series(np.linspace(100.0, 100.0 + n_rows - 1, n_rows))
        preview = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": close - 0.25,
                "high": close + 0.50,
                "low": close - 0.50,
                "close": close,
                "volume": np.linspace(1_000.0, 1_000.0 + n_rows - 1, n_rows),
            }
        )

        if include_auxiliary_sources:
            plan = self.get_source_resolution_plan(target_tf)
            source_names = extra_sources or [
                "mark_price",
                "index_price",
                "premium_price",
                "open_interest",
                "long_short_ratio",
                "funding_rate",
            ]
            for data_type in source_names:
                source_plan = plan.get(data_type, {})
                if source_plan.get("source_tf") is None:
                    continue

                if data_type == "mark_price":
                    preview["markClose"] = preview["close"] * 1.0003
                elif data_type == "index_price":
                    preview["indexClose"] = preview["close"] * 0.9997
                elif data_type == "premium_price":
                    preview["premiumClose"] = preview["close"] * 0.0006
                elif data_type == "open_interest":
                    preview["openInterest"] = np.linspace(
                        10_000.0, 10_000.0 + n_rows - 1, n_rows
                    )
                elif data_type == "long_short_ratio":
                    preview["longShortRatio"] = np.linspace(1.2, 1.4, n_rows)
                elif data_type == "funding_rate":
                    preview["fundingRate"] = np.linspace(0.0001, 0.0002, n_rows)

        feature_preview = self.compute_features(preview, target_tf)
        output_columns = list(feature_preview.columns)
        if include_ohlcv:
            output_columns.extend(["open", "high", "low", "close", "volume"])

        for key, window in (distance_windows or {}).items():
            if key == "dist_avg_high":
                output_columns.append(f"D_dist_avg_high_w{window}")
            elif key == "dist_avg_low":
                output_columns.append(f"D_dist_avg_low_w{window}")
            elif key == "dist_top5_high":
                output_columns.append(f"D_dist_top5_high_w{window}")
            elif key == "dist_bot5_low":
                output_columns.append(f"D_dist_bot5_low_w{window}")

        # Keep the first occurrence order stable.
        return list(dict.fromkeys(output_columns))

    def augment_dataframe_for_timeframe(
        self,
        df_base: pd.DataFrame,
        target_tf: str,
        *,
        extra_sources: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Merge available fetched auxiliary sources onto an existing OHLCV frame.

        This keeps the caller's timestamp range/order while reusing the same
        native/broadcast resolution logic as `load_data_for_timeframe()`.
        """
        plan = self.get_source_resolution_plan(target_tf)
        df = df_base.copy().sort_values("timestamp").reset_index(drop=True)
        source_names = extra_sources or [
            "mark_price",
            "index_price",
            "premium_price",
            "open_interest",
            "long_short_ratio",
            "funding_rate",
        ]

        for data_type in source_names:
            source_plan = plan.get(data_type, {})
            source_tf = source_plan.get("source_tf")
            method = source_plan.get("method")

            if source_tf is None:
                self.log(f"✗ {data_type}: NOT AVAILABLE")
                continue

            df_source = self.load_single_source(data_type, source_tf)
            if df_source is None:
                self.log(f"✗ {data_type}: LOAD FAILED")
                continue

            cols_to_merge: list[str] = []
            for col in df_source.columns:
                if col != "timestamp" and col not in [
                    "buyRatio",
                    "sellRatio",
                    "open",
                    "high",
                    "low",
                ]:
                    cols_to_merge.append(col)

            if not cols_to_merge:
                continue

            existing_cols = [col for col in cols_to_merge if col in df.columns]
            if existing_cols:
                df = df.drop(columns=existing_cols, errors="ignore")

            if method == "native":
                df = df.merge(
                    df_source[["timestamp"] + cols_to_merge],
                    on="timestamp",
                    how="left",
                )
                self.log(f"✓ {data_type} ({source_tf}): {len(df_source):,} rows")
            elif method == "broadcast":
                df = self.align_source_to_base(
                    df,
                    df_source,
                    columns=cols_to_merge,
                    source_tf=source_tf,
                    data_type=data_type,
                    timestamp_role=source_plan.get("timestamp_role"),
                    availability_offset=source_plan.get("availability_offset"),
                    publication_lag=source_plan.get("publication_lag"),
                )
                self.log(
                    f"✓ {data_type} ({source_tf} → {target_tf}): "
                    f"{len(df_source):,} rows (broadcast, "
                    f"role={source_plan.get('timestamp_role')})"
                )

        for col in ["openInterest", "longShortRatio", "fundingRate"]:
            if col in df.columns:
                if col == "longShortRatio":
                    ratio = df[col].replace([np.inf, -np.inf], np.nan)
                    df[col] = ratio.mask(ratio <= 0, np.nan)
                df[col] = df[col].ffill()

        return df

    def align_source_to_base(
        self,
        df_base: pd.DataFrame,
        df_source: pd.DataFrame,
        *,
        columns: list[str],
        source_tf: str,
        data_type: str,
        timestamp_role: str | None = None,
        availability_offset: str | int | float | None = None,
        publication_lag: str | int | float | None = None,
    ) -> pd.DataFrame:
        """
        Align an auxiliary source using explicit source availability semantics.

        Base timestamps are treated as the decision/feature timestamps already
        present in the HTF frame. Source timestamps are shifted to their
        availability time according to `timestamp_role`, then merged with an
        as-of backward join so a row can only see source values whose
        availability timestamp is <= the base timestamp.
        """
        df_base = df_base.copy()
        df_source = df_source.copy()
        source_config = DATA_SOURCE_PATTERNS.get(data_type, {})
        resolved_role = timestamp_role or source_config.get(
            "timestamp_role", "available_at"
        )

        base_key = "_base_available_ts"
        source_key = "_source_available_ts"
        df_base[base_key] = _normalize_timestamp_for_merge(df_base["timestamp"])
        df_source[source_key] = source_available_timestamps(
            df_source["timestamp"],
            source_tf=source_tf,
            timestamp_role=str(resolved_role),
            availability_offset=(
                availability_offset
                if availability_offset is not None
                else source_config.get("availability_offset")
            ),
            publication_lag=(
                publication_lag
                if publication_lag is not None
                else source_config.get("publication_lag")
            ),
        )

        cols_to_merge = [source_key] + [c for c in columns if c in df_source.columns]
        order_col = "_base_order"
        df_base[order_col] = np.arange(len(df_base), dtype=np.int64)
        left = df_base.sort_values(base_key)
        right = (
            df_source[cols_to_merge]
            .dropna(subset=[source_key])
            .sort_values(source_key)
        )

        df_merged = pd.merge_asof(
            left,
            right,
            left_on=base_key,
            right_on=source_key,
            direction="backward",
        )
        df_merged = df_merged.sort_values(order_col).drop(columns=[order_col])
        return df_merged.drop(columns=[base_key, source_key], errors="ignore")

    def broadcast_higher_tf(
        self,
        df_base: pd.DataFrame,
        df_high: pd.DataFrame,
        columns: list[str],
        high_tf: str,
        *,
        timestamp_role: str = "available_at",
        availability_offset: str | int | float | None = "0m",
        publication_lag: str | int | float | None = "0m",
    ) -> pd.DataFrame:
        """
        Compatibility wrapper for higher-timeframe source broadcasts.

        New code should call `align_source_to_base()` with a real data_type so
        timestamp availability semantics come from DATA_SOURCE_PATTERNS.
        """
        return self.align_source_to_base(
            df_base,
            df_high,
            columns=columns,
            source_tf=high_tf,
            data_type="_compat_available_at",
            timestamp_role=timestamp_role,
            availability_offset=availability_offset,
            publication_lag=publication_lag,
        )

    def load_data_for_timeframe(self, target_tf: str) -> pd.DataFrame:
        """
        Load and merge all available data sources for a target timeframe.

        Automatically handles broadcasting from higher TFs when native not available.
        """
        plan = self.get_source_resolution_plan(target_tf)

        self.log(f"\n{'=' * 70}")
        self.log(f"LOADING DATA FOR {target_tf.upper()}")
        self.log(f"{'=' * 70}")

        # 1. Load base OHLCV (must be native)
        ohlcv_plan = plan.get("ohlcv", {})
        if ohlcv_plan.get("source_tf") != target_tf:
            raise ValueError(
                f"OHLCV data not available at native {target_tf}. "
                f"Available: {self.sources.get('ohlcv', DataSourceInfo('ohlcv', [])).available_tfs}"
            )

        df = self.load_single_source("ohlcv", target_tf)
        if df is None:
            raise FileNotFoundError(f"OHLCV data not found for {target_tf}")

        df = df.sort_values("timestamp").reset_index(drop=True)
        self.log(f"✓ OHLCV ({target_tf}): {len(df):,} rows")

        # 2. Load each additional source onto the native OHLCV frame
        df = self.augment_dataframe_for_timeframe(df, target_tf)

        self.log(f"\n→ Final: {len(df):,} rows × {len(df.columns)} columns")
        return df

    def get_window_scaling(self, target_tf: str) -> dict[str, int]:
        """
        Get feature window sizes scaled for the target timeframe.

        Windows are scaled to cover similar time spans:
        - short: ~1h
        - medium: ~2h
        - long: ~4h
        - xlong: ~8h

        Minimum values ensure statistical validity:
        - short: min 2 (for volatility estimators)
        - medium: min 4 (for skew, kurtosis, autocorr)
        - long: min 4 (for drawdown, sharpe, sortino)
        - xlong: min 8 (for long-term patterns)
        """
        tf_mins = parse_timeframe(target_tf)

        return {
            "short": max(2, 60 // tf_mins),  # ~1 hour (min 2 bars)
            "medium": max(4, 120 // tf_mins),  # ~2 hours (min 4 for skew/kurt)
            "long": max(4, 240 // tf_mins),  # ~4 hours
            "xlong": max(8, 480 // tf_mins),  # ~8 hours
        }

    def compute_features(self, df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
        """
        Compute all features for the given data.

        Features are automatically scaled based on timeframe.
        Missing data columns gracefully result in NaN features.
        """
        windows = self.get_window_scaling(target_tf)
        w_short = windows["short"]
        w_med = windows["medium"]
        w_long = windows["long"]
        w_xlong = windows["xlong"]

        features = pd.DataFrame()
        features["timestamp"] = df["timestamp"]

        self.log(
            f"\nComputing {target_tf} features "
            f"(windows: {w_short}/{w_med}/{w_long}/{w_xlong})..."
        )

        # =====================================================================
        # MOMENTUM & PRICE
        # =====================================================================
        features["M_P_logReturn_pct"] = _compute_log_return(df)

        for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
            features[f"M_P_roc_{label}_pct"] = _compute_roc(df, n)
            features[f"M_P_V_momAtr_{label}_rat"] = _compute_mom_atr(df, n)

        # =====================================================================
        # VOLATILITY
        # =====================================================================
        for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
            features[f"V_atrPct_{label}_pct"] = _compute_atr_pct(df, n)
            features[f"V_returnStd_{label}_pct"] = _compute_return_std(df, n)
            features[f"V_parkinson_{label}_pct"] = _compute_parkinson_vol(df, n)
            features[f"V_garmanKlass_{label}_pct"] = _compute_garman_klass_vol(df, n)
            features[f"V_yangZhang_{label}_pct"] = _compute_yang_zhang_vol(df, n)

        for n, label in [(w_long, "long"), (w_xlong, "xlong")]:
            features[f"N_V_bollingerBW_{label}_pct"] = _compute_bollinger_bandwidth(
                df, n
            )

        # =====================================================================
        # NORMALIZED PRICE POSITION
        # =====================================================================
        for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
            features[f"N_P_V_pctB_{label}_bnd"] = _compute_pct_b(df, n)

        # =====================================================================
        # TREND
        # =====================================================================
        features["M_T_ppo_short_long_pct"] = _compute_ppo(df, w_short, w_long)
        features["M_T_ppo_med_xlong_pct"] = _compute_ppo(df, w_med, w_xlong)

        for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
            features[f"N_P_T_priceSmaDeviation_{label}_pct"] = (
                _compute_price_sma_deviation(df, n)
            )
            features[f"N_P_T_priceEmaDeviation_{label}_pct"] = (
                _compute_price_ema_deviation(df, n)
            )

        # =====================================================================
        # OSCILLATORS
        # =====================================================================
        for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
            features[f"M_N_rsi_{label}_bnd"] = _compute_rsi(df, n)
            features[f"M_N_stochasticK_{label}_bnd"] = _compute_stochastic_k(df, n)
            features[f"M_N_T_stochasticD_{label}_bnd"] = _compute_stochastic_d(df, n)

        # =====================================================================
        # VOLUME
        # =====================================================================
        for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
            features[f"L_M_N_volumeRoc_{label}_pct"] = _compute_volume_roc(df, n)
            features[f"L_N_volumeRatio_{label}_rat"] = _compute_volume_ratio(df, n)

        for n, label in [(w_long, "long"), (w_xlong, "xlong")]:
            features[f"L_M_S_obv_{label}_zsc"] = _compute_obv_zscore(df, n)
            features[f"L_M_S_mfi_{label}_bnd"] = _compute_mfi(df, n)
            features[f"L_M_S_cmf_{label}_bnd"] = _compute_cmf(df, n)

        # =====================================================================
        # TREND STRENGTH
        # =====================================================================
        for n, label in [(w_short, "short"), (w_med, "med")]:
            features[f"M_T_V_adx_{label}_bnd"] = _compute_adx(df, n)
            features[f"M_T_V_diDiff_{label}_bnd"] = _compute_di_diff(df, n)
            features[f"N_M_cci_{label}_zsc"] = _compute_cci(df, n)

        # =====================================================================
        # REGIME DETECTION
        # =====================================================================
        for n, label in [(w_med, "med"), (w_long, "long")]:
            features[f"V_autocorr_{label}_bnd"] = _compute_autocorr(df, n)
            features[f"N_P_zScore_{label}_zsc"] = _compute_price_zscore(df, n)
            features[f"V_volMomentum_{label}_pct"] = _compute_vol_momentum(df, n)

        # =====================================================================
        # DISTRIBUTION SHAPE
        # =====================================================================
        for n, label in [(w_med, "med"), (w_long, "long"), (w_xlong, "xlong")]:
            features[f"V_skew_{label}_rat"] = _compute_skew(df, n)
            features[f"V_kurtosis_{label}_rat"] = _compute_kurtosis(df, n)

        # =====================================================================
        # RISK METRICS
        # =====================================================================
        for n, label in [(w_long, "long"), (w_xlong, "xlong")]:
            features[f"V_maxDrawdown_{label}_pct"] = _compute_max_drawdown(df, n)
            features[f"M_V_sharpe_{label}_rat"] = _compute_sharpe(df, n)
            features[f"M_V_sortino_{label}_rat"] = _compute_sortino(df, n)

        # =====================================================================
        # CANDLESTICK
        # =====================================================================
        features["C_N_bodySize_bnd"] = _compute_body_size(df)
        features["C_N_upperShadow_bnd"] = _compute_upper_shadow(df)
        features["C_N_lowerShadow_bnd"] = _compute_lower_shadow(df)
        features["B_C_candleDirection_bin"] = _compute_candle_direction(df)
        features["B_consecutiveUp_bnd"] = _compute_consecutive_up(df)
        features["B_consecutiveDown_bnd"] = _compute_consecutive_down(df)

        for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
            features[f"M_winRate_{label}_bnd"] = _compute_win_rate(df, n)

        # =====================================================================
        # OPEN INTEREST (if available)
        # =====================================================================
        if "openInterest" in df.columns and df["openInterest"].notna().any():
            features["L_M_N_S_oiPctChange_pct"] = _compute_oi_pct_change(df)
            features["L_N_volOiRatio_rat"] = _compute_vol_oi_ratio(df)
            for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
                features[f"L_M_N_S_oiRoc_{label}_pct"] = _compute_oi_roc(df, n)
            self.log("  + Open Interest features")

        # =====================================================================
        # FUNDING (if available)
        # =====================================================================
        if "fundingRate" in df.columns and df["fundingRate"].notna().any():
            for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
                features[f"F_I_fundingCumulative_{label}_pct"] = (
                    _compute_funding_cumulative(df, n)
                )
                features[f"F_I_T_fundingMa_{label}_pct"] = _compute_funding_ma(df, n)
            for n, label in [(w_long, "long"), (w_xlong, "xlong")]:
                features[f"F_I_N_S_fundingZscore_{label}_zsc"] = (
                    _compute_funding_zscore(df, n)
                )
            self.log("  + Funding features")

        # =====================================================================
        # LONG/SHORT RATIO (if available)
        # =====================================================================
        if "longShortRatio" in df.columns and df["longShortRatio"].notna().any():
            features["S_longShortRatio_rat"] = _compute_long_short_ratio(df)
            for n, label in [(w_short, "short"), (w_med, "med")]:
                features[f"S_M_longShortChange_{label}_pct"] = (
                    _compute_long_short_change(df, n)
                )
            for n, label in [(w_long, "long"), (w_xlong, "xlong")]:
                features[f"S_N_longShortZscore_{label}_zsc"] = (
                    _compute_long_short_zscore(df, n)
                )
            self.log("  + Long/Short Ratio features")

        # =====================================================================
        # DERIVATIVES (if available)
        # =====================================================================
        if "indexClose" in df.columns and df["indexClose"].notna().any():
            features["D_F_basis_pct"] = _compute_basis(df)
            self.log("  + Basis (index) features")

        if "markClose" in df.columns and df["markClose"].notna().any():
            features["D_N_markCloseDeviation_pct"] = _compute_mark_close_deviation(df)
            self.log("  + Mark price features")

        if "premiumClose" in df.columns and df["premiumClose"].notna().any():
            for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
                features[f"D_F_T_premiumMa_{label}_pct"] = _compute_premium_ma(df, n)
            for n, label in [(w_long, "long"), (w_xlong, "xlong")]:
                features[f"D_F_N_S_premiumZscore_{label}_zsc"] = (
                    _compute_premium_zscore(df, n)
                )
            self.log("  + Premium features")

        # =====================================================================
        # COMPOSITE DERIVATIVES PRESSURE (if available)
        # =====================================================================
        composite_count = 0
        returns = features["M_P_logReturn_pct"]

        if "L_M_N_S_oiPctChange_pct" in features.columns:
            doi = features["L_M_N_S_oiPctChange_pct"]
            for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
                features[f"X_D_oiRetPressure_{label}_pct"] = _rolling_mean_product(
                    doi, returns, n
                )
                composite_count += 1

        if "D_F_basis_pct" in features.columns:
            basis = features["D_F_basis_pct"]
            for n, label in [(w_short, "short"), (w_med, "med"), (w_long, "long")]:
                features[f"X_D_basisRetPressure_{label}_pct"] = (
                    _rolling_mean_product(basis, returns, n)
                )
                composite_count += 1

            if "fundingRate" in df.columns and df["fundingRate"].notna().any():
                funding_rate = df["fundingRate"]
                for n, label in [(w_long, "long"), (w_xlong, "xlong")]:
                    features[f"X_D_fundingBasisPressure_{label}_pct"] = (
                        _rolling_mean_product(funding_rate, basis, n)
                    )
                    composite_count += 1

        if "longShortRatio" in df.columns and df["longShortRatio"].notna().any():
            dls = _compute_long_short_pct_change(df)
            for n, label in [(w_long, "long"), (w_xlong, "xlong")]:
                features[f"X_D_longShortRetPressure_{label}_pct"] = (
                    _rolling_mean_product(dls, returns, n)
                )
                composite_count += 1

        if composite_count:
            self.log(f"  + Composite derivatives pressure features ({composite_count})")

        # =====================================================================
        # SUMMARY
        # =====================================================================
        feature_cols = [c for c in features.columns if c != "timestamp"]
        self.log(f"\n→ Computed {len(feature_cols)} features")

        # Count valid values
        valid_counts = features[feature_cols].notna().sum()
        self.log(
            f"→ Valid values range: {valid_counts.min():,} - {valid_counts.max():,}"
        )

        return features


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================


def load_and_compute_htf_features(
    data_dir: Path,
    timeframe: str,
    save_path: Path | None = None,
    include_ohlcv: bool = True,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Load raw data and compute all features for a timeframe.

    Args:
        data_dir: Path to fetchingByBit directory
        timeframe: Any valid timeframe (1m, 5m, 15m, 1h, etc.)
        save_path: Optional path to save features parquet
        include_ohlcv: Whether to include OHLCV columns in output
        verbose: Print progress messages

    Returns:
        DataFrame with timestamp, (optionally OHLCV), and all computed features
    """
    engine = HTFFeatureEngine(data_dir=data_dir, verbose=verbose)
    engine.discover_available_sources()

    # Load data
    df_raw = engine.load_data_for_timeframe(timeframe)

    # Compute features
    df_features = engine.compute_features(df_raw, timeframe)

    # Optionally include OHLCV
    if include_ohlcv:
        ohlcv_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        existing_ohlcv = [c for c in ohlcv_cols if c in df_raw.columns]
        df_result = df_raw[existing_ohlcv].merge(
            df_features, on="timestamp", how="left"
        )
    else:
        df_result = df_features

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        df_result.to_parquet(save_path)
        if verbose:
            print(f"\n✓ Saved to: {save_path}")

    if verbose:
        print(f"\n{'=' * 70}")
        print(f"FINAL: {df_result.shape[0]:,} rows × {df_result.shape[1]} columns")
        print(f"{'=' * 70}")

    return df_result


# =============================================================================
# FEATURE COMPUTATION FUNCTIONS (all private, prefixed with _)
# =============================================================================


def _compute_atr(df: pd.DataFrame, n: int) -> pd.Series:
    """ATR - Average True Range"""
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1)),
        ),
    )
    return tr.ewm(span=n, adjust=False).mean()


def _compute_log_return(df: pd.DataFrame) -> pd.Series:
    """Log return: ln(close_t / close_{t-1})"""
    return np.log(df["close"] / df["close"].shift(1))


def _compute_roc(df: pd.DataFrame, n: int) -> pd.Series:
    """Rate of change: (close_t - close_{t-n}) / close_{t-n}"""
    return (df["close"] - df["close"].shift(n)) / df["close"].shift(n)


def _compute_mom_atr(df: pd.DataFrame, n: int) -> pd.Series:
    """Momentum / ATR"""
    atr = _compute_atr(df, n)
    return (df["close"] - df["close"].shift(n)) / atr


def _compute_atr_pct(df: pd.DataFrame, n: int) -> pd.Series:
    """ATR as percentage of close"""
    atr = _compute_atr(df, n)
    return atr / df["close"]


def _compute_return_std(df: pd.DataFrame, n: int) -> pd.Series:
    """Rolling std of log returns"""
    log_ret = np.log(df["close"] / df["close"].shift(1))
    return log_ret.rolling(n).std()


def _compute_pct_b(df: pd.DataFrame, n: int) -> pd.Series:
    """Bollinger %B: (close - lower) / (upper - lower)"""
    sma = df["close"].rolling(n).mean()
    std = df["close"].rolling(n).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    return (df["close"] - lower) / (upper - lower)


def _compute_bollinger_bandwidth(df: pd.DataFrame, n: int) -> pd.Series:
    """Bollinger bandwidth: (upper - lower) / sma"""
    sma = df["close"].rolling(n).mean()
    std = df["close"].rolling(n).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    return (upper - lower) / sma


def _compute_ppo(df: pd.DataFrame, short: int, long: int) -> pd.Series:
    """Price Percentage Oscillator"""
    ema_short = df["close"].ewm(span=short, adjust=False).mean()
    ema_long = df["close"].ewm(span=long, adjust=False).mean()
    return (ema_short - ema_long) / ema_long * 100


def _compute_price_sma_deviation(df: pd.DataFrame, n: int) -> pd.Series:
    """Price deviation from SMA"""
    sma = df["close"].rolling(n).mean()
    return (df["close"] - sma) / sma


def _compute_price_ema_deviation(df: pd.DataFrame, n: int) -> pd.Series:
    """Price deviation from EMA"""
    ema = df["close"].ewm(span=n, adjust=False).mean()
    return (df["close"] - ema) / ema


def _compute_rsi(df: pd.DataFrame, n: int) -> pd.Series:
    """RSI - Relative Strength Index"""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(n).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _compute_stochastic_k(df: pd.DataFrame, n: int) -> pd.Series:
    """Stochastic %K"""
    lowest = df["low"].rolling(n).min()
    highest = df["high"].rolling(n).max()
    return (df["close"] - lowest) / (highest - lowest) * 100


def _compute_stochastic_d(df: pd.DataFrame, n: int, smooth: int = 3) -> pd.Series:
    """Stochastic %D"""
    k = _compute_stochastic_k(df, n)
    return k.rolling(smooth).mean()


def _compute_volume_roc(df: pd.DataFrame, n: int) -> pd.Series:
    """Volume rate of change"""
    return (df["volume"] - df["volume"].shift(n)) / df["volume"].shift(n)


def _compute_volume_ratio(df: pd.DataFrame, n: int) -> pd.Series:
    """Volume / SMA(volume)"""
    sma = df["volume"].rolling(n).mean()
    return df["volume"] / sma


def _compute_obv_zscore(df: pd.DataFrame, n: int) -> pd.Series:
    """On-Balance Volume, z-scored"""
    log_ret = np.log(df["close"] / df["close"].shift(1))
    signed_vol = np.sign(log_ret) * df["volume"]
    obv = signed_vol.cumsum()
    mean = obv.rolling(n).mean()
    std = obv.rolling(n).std()
    return ((obv - mean) / std.replace(0, np.nan)).clip(-4, 4)


def _compute_mfi(df: pd.DataFrame, n: int) -> pd.Series:
    """Money Flow Index"""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mf = tp * df["volume"]
    tp_diff = tp.diff()
    pos_mf = mf.where(tp_diff > 0, 0).rolling(n).sum()
    neg_mf = mf.where(tp_diff < 0, 0).rolling(n).sum()
    ratio = pos_mf / neg_mf.replace(0, np.nan)
    return 100 - (100 / (1 + ratio))


def _compute_cmf(df: pd.DataFrame, n: int) -> pd.Series:
    """Chaikin Money Flow"""
    range_ = (df["high"] - df["low"]).replace(0, np.nan)
    mf_mult = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / range_
    mf_mult = mf_mult.fillna(0)
    mf_vol = mf_mult * df["volume"]
    return mf_vol.rolling(n).sum() / df["volume"].rolling(n).sum()


def _compute_adx(df: pd.DataFrame, n: int) -> pd.Series:
    """Average Directional Index"""
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1)),
        ),
    )
    up_move = df["high"] - df["high"].shift(1)
    down_move = df["low"].shift(1) - df["low"]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    atr = tr.ewm(span=n, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(span=n, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(span=n, adjust=False).mean() / atr

    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(span=n, adjust=False).mean()


def _compute_di_diff(df: pd.DataFrame, n: int) -> pd.Series:
    """DI difference: (+DI - -DI) / 100"""
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1)),
        ),
    )
    up_move = df["high"] - df["high"].shift(1)
    down_move = df["low"].shift(1) - df["low"]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    atr = tr.ewm(span=n, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(span=n, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(span=n, adjust=False).mean() / atr

    return (plus_di - minus_di) / 100


def _compute_cci(df: pd.DataFrame, n: int) -> pd.Series:
    """Commodity Channel Index"""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(n).mean()
    mean_dev = abs(tp - sma_tp).rolling(n).mean()
    return ((tp - sma_tp) / (0.015 * mean_dev).replace(0, np.nan)).clip(-300, 300)


@numba.njit(cache=True)
def _autocorr_kernel(returns: np.ndarray, n: int) -> np.ndarray:
    """Numba kernel for exact lag-1 autocorrelation (matches pandas autocorr)."""
    length = len(returns)
    result = np.empty(length, dtype=np.float64)
    result[:] = np.nan

    for i in range(n, length):
        # Window of returns [i-n+1 : i+1]
        window = returns[i - n + 1 : i + 1]

        # Skip if any NaN in window
        has_nan = False
        for v in window:
            if np.isnan(v):
                has_nan = True
                break
        if has_nan:
            continue

        # For lag-1 autocorr, we correlate x[1:n] with x[0:n-1]
        # Using Pearson correlation formula
        n_pairs = n - 1  # number of valid pairs

        # Compute means of both series
        sum_x = 0.0
        sum_y = 0.0
        for j in range(1, n):
            sum_x += window[j]
            sum_y += window[j - 1]
        mean_x = sum_x / n_pairs
        mean_y = sum_y / n_pairs

        # Compute covariance and standard deviations
        cov = 0.0
        var_x = 0.0
        var_y = 0.0
        for j in range(1, n):
            dx = window[j] - mean_x
            dy = window[j - 1] - mean_y
            cov += dx * dy
            var_x += dx * dx
            var_y += dy * dy

        if var_x > 0 and var_y > 0:
            result[i] = cov / np.sqrt(var_x * var_y)
        else:
            result[i] = np.nan

    return result


def _compute_autocorr(df: pd.DataFrame, n: int) -> pd.Series:
    """Lag-1 autocorrelation of returns - exact numba implementation."""
    log_ret = np.log(df["close"].values / np.roll(df["close"].values, 1))
    log_ret[0] = np.nan  # First return is invalid
    result = _autocorr_kernel(log_ret, n)
    return pd.Series(result, index=df.index).clip(-1, 1)


def _compute_price_zscore(df: pd.DataFrame, n: int) -> pd.Series:
    """Price z-score"""
    mean = df["close"].rolling(n).mean()
    std = df["close"].rolling(n).std()
    return ((df["close"] - mean) / std.replace(0, np.nan)).clip(-4, 4)


def _compute_vol_momentum(df: pd.DataFrame, n: int) -> pd.Series:
    """Volatility momentum"""
    log_ret = np.log(df["close"] / df["close"].shift(1))
    m = max(n // 2, 2)
    ret_std = log_ret.rolling(m).std()
    return ((ret_std / ret_std.shift(n)) - 1).clip(-1, 15)


def _compute_skew(df: pd.DataFrame, n: int) -> pd.Series:
    """Rolling skewness"""
    log_ret = np.log(df["close"] / df["close"].shift(1))
    return log_ret.rolling(n).skew().clip(-3, 3)


def _compute_kurtosis(df: pd.DataFrame, n: int) -> pd.Series:
    """Rolling kurtosis"""
    log_ret = np.log(df["close"] / df["close"].shift(1))
    return log_ret.rolling(n).kurt().clip(-3, 10)


def _compute_parkinson_vol(df: pd.DataFrame, n: int) -> pd.Series:
    """Parkinson volatility estimator"""
    log_hl = np.log(df["high"] / df["low"])
    const = 1 / (4 * np.log(2))
    var = const * (log_hl**2)
    return np.sqrt(var.rolling(n).mean())


def _compute_garman_klass_vol(df: pd.DataFrame, n: int) -> pd.Series:
    """Garman-Klass volatility estimator"""
    log_hl = np.log(df["high"] / df["low"])
    log_co = np.log(df["close"] / df["open"])
    gk_const = 2 * np.log(2) - 1
    var = 0.5 * (log_hl**2) - gk_const * (log_co**2)
    return np.sqrt(np.abs(var.rolling(n).mean()))


def _compute_yang_zhang_vol(df: pd.DataFrame, n: int) -> pd.Series:
    """Yang-Zhang volatility estimator"""
    # Guard against n <= 1 (causes division by zero in k calculation)
    if n <= 1:
        return pd.Series(np.nan, index=df.index)

    log_oc = np.log(df["close"] / df["open"])
    mean_oc = log_oc.rolling(n).mean()
    var_oc = ((log_oc - mean_oc) ** 2).rolling(n).mean()

    log_hc = np.log(df["high"] / df["close"])
    log_ho = np.log(df["high"] / df["open"])
    log_lc = np.log(df["low"] / df["close"])
    log_lo = np.log(df["low"] / df["open"])
    var_rs = (log_hc * log_ho + log_lc * log_lo).rolling(n).mean()

    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    var = k * var_oc + (1 - k) * np.abs(var_rs)
    return np.sqrt(np.abs(var))


def _compute_body_size(df: pd.DataFrame) -> pd.Series:
    """Candle body size / range"""
    range_ = df["high"] - df["low"]
    ratio = abs(df["close"] - df["open"]) / range_.replace(0, np.nan)
    return ratio.mask(range_.eq(0), 0.0)


def _compute_upper_shadow(df: pd.DataFrame) -> pd.Series:
    """Upper shadow / range"""
    range_ = df["high"] - df["low"]
    ratio = (df["high"] - np.maximum(df["open"], df["close"])) / range_.replace(0, np.nan)
    return ratio.mask(range_.eq(0), 0.0)


def _compute_lower_shadow(df: pd.DataFrame) -> pd.Series:
    """Lower shadow / range"""
    range_ = df["high"] - df["low"]
    ratio = (np.minimum(df["open"], df["close"]) - df["low"]) / range_.replace(0, np.nan)
    return ratio.mask(range_.eq(0), 0.0)


def _compute_candle_direction(df: pd.DataFrame) -> pd.Series:
    """Candle direction: +1 bullish, -1 bearish"""
    return np.sign(df["close"] - df["open"])


def _compute_consecutive_up(df: pd.DataFrame) -> pd.Series:
    """Count of consecutive up bars"""
    direction = (df["close"] > df["close"].shift(1)).astype(int)
    result = []
    count = 0
    for val in direction:
        if val == 1:
            count += 1
        else:
            count = 0
        result.append(count)
    return pd.Series(result, index=df.index).clip(0, 10)


def _compute_consecutive_down(df: pd.DataFrame) -> pd.Series:
    """Count of consecutive down bars"""
    direction = (df["close"] < df["close"].shift(1)).astype(int)
    result = []
    count = 0
    for val in direction:
        if val == 1:
            count += 1
        else:
            count = 0
        result.append(count)
    return pd.Series(result, index=df.index).clip(0, 10)


def _compute_win_rate(df: pd.DataFrame, n: int) -> pd.Series:
    """Win rate over n periods"""
    log_ret = np.log(df["close"] / df["close"].shift(1))
    positive = (log_ret > 0).astype(int)
    return positive.rolling(n).mean()


@numba.njit(cache=True)
def _max_drawdown_kernel(prices: np.ndarray, n: int) -> np.ndarray:
    """Numba kernel for exact rolling max drawdown (peak-to-trough)."""
    length = len(prices)
    result = np.empty(length, dtype=np.float64)
    result[:] = np.nan

    for i in range(n - 1, length):
        # Window of prices [i-n+1 : i+1]
        window_start = i - n + 1
        window_end = i + 1

        # Track running peak and max drawdown
        running_peak = prices[window_start]
        max_dd = 0.0

        for j in range(window_start, window_end):
            price = prices[j]
            if np.isnan(price):
                max_dd = np.nan
                break

            if price > running_peak:
                running_peak = price

            if running_peak > 0:
                dd = (price - running_peak) / running_peak
                if dd < max_dd:
                    max_dd = dd

        result[i] = max_dd

    return result


def _compute_max_drawdown(df: pd.DataFrame, n: int) -> pd.Series:
    """Maximum drawdown over n periods - exact numba implementation."""
    prices = df["close"].values.astype(np.float64)
    result = _max_drawdown_kernel(prices, n)
    return pd.Series(result, index=df.index).clip(-1, 0)


def _compute_sharpe(df: pd.DataFrame, n: int) -> pd.Series:
    """Rolling Sharpe ratio"""
    log_ret = np.log(df["close"] / df["close"].shift(1))
    mean_ret = log_ret.rolling(n).mean()
    std_ret = log_ret.rolling(n).std()
    return ((mean_ret / std_ret.replace(0, np.nan)) * np.sqrt(n)).clip(-5, 5)


@numba.njit(cache=True)
def _sortino_kernel(returns: np.ndarray, n: int) -> np.ndarray:
    """Numba kernel for exact rolling Sortino ratio (matches pandas std ddof=1)."""
    length = len(returns)
    result = np.empty(length, dtype=np.float64)
    result[:] = np.nan

    for i in range(n - 1, length):
        # Window of returns [i-n+1 : i+1]
        window_start = i - n + 1
        window_end = i + 1

        # Compute mean return
        sum_ret = 0.0
        count_valid = 0
        has_nan = False

        for j in range(window_start, window_end):
            if np.isnan(returns[j]):
                has_nan = True
                break
            sum_ret += returns[j]
            count_valid += 1

        if has_nan or count_valid < 2:
            continue

        mean_ret = sum_ret / count_valid

        # Downside deviation: sample std of returns < 0 (ddof=1 like pandas)
        # First collect negative returns
        neg_returns = np.empty(n, dtype=np.float64)
        count_neg = 0

        for j in range(window_start, window_end):
            if returns[j] < 0:
                neg_returns[count_neg] = returns[j]
                count_neg += 1

        if count_neg >= 2:
            # Compute mean of negative returns
            sum_neg = 0.0
            for k in range(count_neg):
                sum_neg += neg_returns[k]
            mean_neg = sum_neg / count_neg

            # Compute sample variance (ddof=1)
            sum_sq_diff = 0.0
            for k in range(count_neg):
                diff = neg_returns[k] - mean_neg
                sum_sq_diff += diff * diff

            down_std = np.sqrt(sum_sq_diff / (count_neg - 1))  # ddof=1
            if down_std > 0:
                result[i] = (mean_ret / down_std) * np.sqrt(n)

    return result


def _compute_sortino(df: pd.DataFrame, n: int) -> pd.Series:
    """Rolling Sortino ratio - exact numba implementation."""
    log_ret = np.log(df["close"].values / np.roll(df["close"].values, 1))
    log_ret[0] = np.nan  # First return is invalid
    result = _sortino_kernel(log_ret, n)
    return pd.Series(result, index=df.index).clip(-5, 5)


# Features using additional data sources
def _compute_oi_pct_change(df: pd.DataFrame) -> pd.Series:
    """Open Interest percentage change"""
    if "openInterest" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return (df["openInterest"] - df["openInterest"].shift(1)) / df[
        "openInterest"
    ].shift(1)


def _compute_oi_roc(df: pd.DataFrame, n: int) -> pd.Series:
    """Open Interest rate of change"""
    if "openInterest" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return (df["openInterest"] - df["openInterest"].shift(n)) / df[
        "openInterest"
    ].shift(n)


def _compute_vol_oi_ratio(df: pd.DataFrame) -> pd.Series:
    """Volume / Open Interest"""
    if "openInterest" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return df["volume"] / df["openInterest"]


def _compute_funding_cumulative(df: pd.DataFrame, n: int) -> pd.Series:
    """Cumulative funding rate"""
    if "fundingRate" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return df["fundingRate"].rolling(n, min_periods=1).sum()


def _compute_funding_ma(df: pd.DataFrame, n: int) -> pd.Series:
    """Funding rate moving average"""
    if "fundingRate" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return df["fundingRate"].rolling(n, min_periods=1).mean()


def _compute_funding_zscore(df: pd.DataFrame, n: int) -> pd.Series:
    """Funding rate z-score"""
    if "fundingRate" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    mu = df["fundingRate"].rolling(n).mean()
    sigma = df["fundingRate"].rolling(n).std()
    zscore = (df["fundingRate"] - mu) / sigma.replace(0, np.nan)
    return zscore.clip(-5, 5)


def _compute_long_short_ratio(df: pd.DataFrame) -> pd.Series:
    """Long/Short ratio (raw)"""
    if "longShortRatio" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    ls = df["longShortRatio"].replace([np.inf, -np.inf], np.nan)
    return ls.mask(ls <= 0, np.nan)


def _compute_long_short_zscore(df: pd.DataFrame, n: int) -> pd.Series:
    """Long/Short ratio z-score"""
    ls = _compute_long_short_ratio(df)
    mean = ls.rolling(n).mean()
    std = ls.rolling(n).std()
    zscore = pd.Series(np.nan, index=df.index, dtype=np.float64)
    ready = mean.notna() & std.notna()
    nonflat = ready & (std > 0)
    flat = ready & (std == 0)

    zscore.loc[nonflat] = (ls.loc[nonflat] - mean.loc[nonflat]) / std.loc[nonflat]
    # A fully flat rolling window is a neutral crowding state, not a missing
    # observation. Emit 0.0 so downstream model inputs stay usable.
    zscore.loc[flat] = 0.0
    return zscore.clip(-5, 5)


def _compute_long_short_change(df: pd.DataFrame, n: int) -> pd.Series:
    """Long/Short ratio change"""
    ls = _compute_long_short_ratio(df)
    return ((ls / ls.shift(n)).replace([np.inf, -np.inf], np.nan) - 1).clip(-1, 1)


def _compute_basis(df: pd.DataFrame) -> pd.Series:
    """Basis: (close - indexClose) / indexClose"""
    if "indexClose" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return (df["close"] - df["indexClose"]) / df["indexClose"]


def _compute_mark_close_deviation(df: pd.DataFrame) -> pd.Series:
    """(close - markClose) / markClose"""
    if "markClose" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return (df["close"] - df["markClose"]) / df["markClose"]


def _compute_premium_ma(df: pd.DataFrame, n: int) -> pd.Series:
    """Premium moving average"""
    if "premiumClose" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return df["premiumClose"].rolling(n, min_periods=1).mean()


def _compute_premium_zscore(df: pd.DataFrame, n: int) -> pd.Series:
    """Premium z-score"""
    if "premiumClose" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    mu = df["premiumClose"].rolling(n).mean()
    sigma = df["premiumClose"].rolling(n).std()
    return ((df["premiumClose"] - mu) / sigma.replace(0, np.nan)).clip(-5, 5)


def _rolling_mean_product(lhs: pd.Series, rhs: pd.Series, n: int) -> pd.Series:
    """Rolling mean of a causal elementwise product."""
    return (lhs * rhs).rolling(n).mean()


def _compute_long_short_pct_change(df: pd.DataFrame) -> pd.Series:
    """One-step percentage change on the broadcast-aligned long/short ratio."""
    ls = _compute_long_short_ratio(df)
    return ls.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compute HTF features")
    parser.add_argument(
        "--timeframe",
        "-t",
        default="5m",
        help="Timeframe (1m, 5m, 15m, 1h, etc.)",
    )
    parser.add_argument(
        "--data-dir",
        "-d",
        type=Path,
        default=Path("fetchingByBit"),
        help="Data directory",
    )
    parser.add_argument("--output", "-o", type=Path, help="Output path")

    args = parser.parse_args()

    output = args.output or Path(f"data/htf_features_{args.timeframe}.parquet")

    df = load_and_compute_htf_features(args.data_dir, args.timeframe, output)
    print(f"\nDone! Shape: {df.shape}")
