"""
Pipeline State Management
=========================

Tracks data versions and validates consistency across pipeline steps.

KEY INSIGHT: Expanding rank optimization is NOT incrementally resumable.
When new rows are added, ranks for ALL historical rows change because
the distribution changes.

SOLUTION:
1. Track data hash/version at each step
2. When source data changes → detect and warn
3. For feature optimization: ALWAYS recompute from scratch
4. For features/targets: Can be incrementally updated (row-local computations)

The goal is to DETECT inconsistencies, not hide them.

Usage:
    from scripts.analysis.pipeline_state import PipelineState
    state = PipelineState.load()

    # Check if step needs recompute
    if state.needs_recompute("features"):
        run_feature_engineering()
        state.update("features", new_checksum)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class StepState:
    """State for a single pipeline step."""

    last_run: str | None = None  # ISO timestamp
    row_count: int = 0
    last_timestamp: str | None = None  # Last data timestamp
    checksum: str | None = None  # MD5 of first+last 1000 rows
    schema_hash: str | None = None  # Hash of column names
    config_hash: str | None = None  # Hash of config params (for optimization)

    def to_dict(self) -> dict:
        return {
            "last_run": self.last_run,
            "row_count": self.row_count,
            "last_timestamp": self.last_timestamp,
            "checksum": self.checksum,
            "schema_hash": self.schema_hash,
            "config_hash": self.config_hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StepState":
        return cls(**d)


@dataclass
class PipelineState:
    """
    Tracks state across all pipeline steps.

    Steps tracked:
    - raw_8h: Fetched 8h data from Bybit
    - merged_raw: Merged raw sources
    - features: Computed features
    - analysis: Features + targets
    - optimized_{target}_{horizon}: Optimized feature files
    - datasets_{target}_{horizon}: Final ML-ready datasets
    """

    steps: dict[str, StepState] = field(default_factory=dict)
    version: str = "1.0"

    STATE_FILE = Path("data/.pipeline_state.json")

    @classmethod
    def load(cls, project_root: Path | None = None) -> "PipelineState":
        """Load state from disk or create new."""
        if project_root:
            state_file = project_root / "data" / ".pipeline_state.json"
        else:
            state_file = cls.STATE_FILE

        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                state = cls(
                    version=data.get("version", "1.0"),
                    steps={
                        k: StepState.from_dict(v)
                        for k, v in data.get("steps", {}).items()
                    },
                )
                return state
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not load pipeline state: {e}")
                return cls()
        return cls()

    def save(self, project_root: Path | None = None) -> None:
        """Save state to disk."""
        if project_root:
            state_file = project_root / "data" / ".pipeline_state.json"
        else:
            state_file = self.STATE_FILE

        state_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": self.version,
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "last_saved": datetime.now(timezone.utc).isoformat(),
        }

        with open(state_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_step(self, step_name: str) -> StepState:
        """Get state for a step (creates if not exists)."""
        if step_name not in self.steps:
            self.steps[step_name] = StepState()
        return self.steps[step_name]

    def update_step(
        self,
        step_name: str,
        row_count: int,
        last_timestamp: str,
        checksum: str | None = None,
        schema_hash: str | None = None,
        config_hash: str | None = None,
    ) -> None:
        """Update state after running a step."""
        step = self.get_step(step_name)
        step.last_run = datetime.now(timezone.utc).isoformat()
        step.row_count = row_count
        step.last_timestamp = last_timestamp
        if checksum:
            step.checksum = checksum
        if schema_hash:
            step.schema_hash = schema_hash
        if config_hash:
            step.config_hash = config_hash


def compute_data_checksum(df, n_rows: int = 1000) -> str:
    """
    Compute checksum from first and last N rows.

    This detects:
    - Changes to historical data (first rows)
    - New data additions (last rows)
    - Data corruption
    """
    import polars as pl

    if isinstance(df, pl.DataFrame):
        df = df.to_pandas()

    # Get first and last n_rows
    first_part = df.head(min(n_rows, len(df)))
    last_part = df.tail(min(n_rows, len(df)))

    # Convert to string representation
    first_str = first_part.to_csv(index=False)
    last_str = last_part.to_csv(index=False)

    # Compute hash
    combined = f"{first_str}\n---\n{last_str}"
    return hashlib.md5(combined.encode()).hexdigest()[:16]


def compute_schema_hash(df) -> str:
    """Compute hash of column names and dtypes."""
    import polars as pl

    if isinstance(df, pl.DataFrame):
        schema_str = str(sorted([(c, str(df[c].dtype)) for c in df.columns]))
    else:
        schema_str = str(sorted([(c, str(df[c].dtype)) for c in df.columns]))

    return hashlib.md5(schema_str.encode()).hexdigest()[:16]


def compute_config_hash(config: dict) -> str:
    """Compute hash of configuration dictionary."""
    config_str = json.dumps(config, sort_keys=True, default=str)
    return hashlib.md5(config_str.encode()).hexdigest()[:16]


def check_consistency(
    step_name: str,
    current_checksum: str,
    current_schema_hash: str,
    state: PipelineState,
) -> dict[str, Any]:
    """
    Check if current data is consistent with saved state.

    Returns:
        dict with:
        - is_consistent: bool
        - reason: str (if inconsistent)
        - action: str (suggested action)
    """
    step = state.get_step(step_name)

    if step.checksum is None:
        return {
            "is_consistent": True,
            "reason": "No previous state (first run)",
            "action": "proceed",
        }

    # Check schema first (critical)
    if step.schema_hash and step.schema_hash != current_schema_hash:
        return {
            "is_consistent": False,
            "reason": f"Schema changed! Old={step.schema_hash}, New={current_schema_hash}",
            "action": "FULL_RECOMPUTE_REQUIRED",
        }

    # Check data checksum
    if step.checksum != current_checksum:
        return {
            "is_consistent": False,
            "reason": f"Data checksum changed. Old={step.checksum}, New={current_checksum}",
            "action": "recompute_downstream",
        }

    return {
        "is_consistent": True,
        "reason": "Checksums match",
        "action": "skip_if_no_new_data",
    }


def validate_optimization_resumability(
    existing_optimized_file: Path,
    current_analysis_file: Path,
    config: dict,
    state: PipelineState,
) -> dict[str, Any]:
    """
    Check if optimization can be incrementally updated.

    CRITICAL: Expanding rank optimization CANNOT be incrementally updated!
    When new rows are added, ALL historical ranks change.

    This function detects when a full recompute is needed.
    """
    import polars as pl

    step_name = (
        existing_optimized_file.stem
    )  # e.g., "features_8h_optimized_direction_1bar"
    step = state.get_step(step_name)

    # Check if config changed
    current_config_hash = compute_config_hash(config)
    if step.config_hash and step.config_hash != current_config_hash:
        return {
            "can_resume": False,
            "reason": "Optimization config changed",
            "action": "FULL_RECOMPUTE",
        }

    # Load current analysis data
    if not current_analysis_file.exists():
        return {
            "can_resume": False,
            "reason": "Analysis file not found",
            "action": "FULL_RECOMPUTE",
        }

    analysis_df = pl.read_parquet(current_analysis_file)
    analysis_rows = len(analysis_df)
    analysis_end = str(analysis_df.select("timestamp").max().item())

    # Check if analysis data changed
    if not existing_optimized_file.exists():
        return {
            "can_resume": False,
            "reason": "No existing optimized file",
            "action": "FULL_COMPUTE",
        }

    opt_df = pl.read_parquet(existing_optimized_file)
    opt_rows = len(opt_df)

    # CRITICAL CHECK: If analysis has MORE rows, we MUST recompute
    # because expanding rank uses all historical data
    if analysis_rows > opt_rows:
        new_rows = analysis_rows - opt_rows
        return {
            "can_resume": False,
            "reason": f"Analysis has {new_rows} new rows - expanding rank requires full recompute",
            "action": "FULL_RECOMPUTE",
            "new_rows": new_rows,
        }

    # If analysis has FEWER rows, something is wrong
    if analysis_rows < opt_rows:
        return {
            "can_resume": False,
            "reason": f"Analysis has FEWER rows ({analysis_rows}) than optimized ({opt_rows}) - data corruption?",
            "action": "FULL_RECOMPUTE",
        }

    # Same row count - check if data changed
    analysis_checksum = compute_data_checksum(analysis_df)
    analysis_schema = compute_schema_hash(analysis_df)

    consistency = check_consistency(
        f"analysis_for_{step_name}",
        analysis_checksum,
        analysis_schema,
        state,
    )

    if not consistency["is_consistent"]:
        return {
            "can_resume": False,
            "reason": consistency["reason"],
            "action": "FULL_RECOMPUTE",
        }

    return {
        "can_resume": True,
        "reason": "Data unchanged, optimization is current",
        "action": "SKIP",
    }


def print_pipeline_status(state: PipelineState, project_root: Path) -> None:
    """Print current pipeline status."""
    import polars as pl

    print("=" * 70)
    print("PIPELINE STATE STATUS")
    print("=" * 70)

    files_to_check = [
        (
            "raw_8h",
            project_root
            / "fetchingByBit"
            / "sorted-8h-bybit-linear"
            / "BTCUSDT.parquet",
        ),
        ("merged_raw", project_root / "data" / "merged_8h_raw.parquet"),
        ("features", project_root / "data" / "features_8h.parquet"),
        ("analysis", project_root / "data" / "analysis_8h.parquet"),
    ]

    # Add optimized files
    for f in (project_root / "data").glob("features_8h_optimized_*.parquet"):
        files_to_check.append((f.stem, f))

    print(f"\n{'Step':<45} {'Rows':>8} {'Last Timestamp':>24} {'Status':<10}")
    print("-" * 95)

    for step_name, filepath in files_to_check:
        if filepath.exists():
            try:
                df = pl.read_parquet(filepath)
                rows = len(df)
                if "timestamp" in df.columns:
                    last_ts = str(df.select("timestamp").max().item())[:19]
                else:
                    last_ts = "N/A"

                step = state.get_step(step_name)
                if step.row_count and step.row_count != rows:
                    status = "CHANGED"
                elif step.row_count:
                    status = "OK"
                else:
                    status = "NEW"

                print(f"{step_name:<45} {rows:>8} {last_ts:>24} {status:<10}")
            except Exception as e:
                print(f"{step_name:<45} {'ERROR':>8} {str(e)[:24]:>24} {'ERROR':<10}")
        else:
            print(f"{step_name:<45} {'MISSING':>8} {'N/A':>24} {'MISSING':<10}")

    print()
