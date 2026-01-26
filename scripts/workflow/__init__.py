"""
Workflow orchestration modules for the RiskYieldMM ML pipeline.

This package contains modules that support the main_wf.py notebook:
- config: Workflow configuration (horizons, targets, thresholds)
- data_fetching: Step 0 data fetch & aggregation
- state_detection: Pipeline state and staleness detection
- validation: Causality tests and pipeline verification
- l1_helpers: L1 precomputation helper functions

================================================================================
MODULE REFERENCE GUIDE
================================================================================

config.py - Configuration & Constants
--------------------------------------
Constants:
  WORKFLOW_HORIZONS     List[int]   - Horizons to process [1, 3, 6, 12]
  WORKFLOW_TARGETS      List[str]   - Targets to process
  AUTO_FETCH_IF_STALE   bool        - Auto-fetch from Bybit
  STALE_THRESHOLD_HOURS int         - Hours before data is stale
  L1_CONFIG_MODE        str         - "1bar", "reduced", or "all"
  L1_ROWS               int|None    - Backtest iterations (None=auto)
  L1_HELPERS            List[str]   - Helper names for L1
  EXPECTED_FEATURES     int         - Expected feature count
  ENABLE_BOOSTING       bool        - Enable ICIR selection

Classes:
  WorkflowConfig        - Dataclass with all settings + print_summary()

Functions:
  get_workflow_config() -> WorkflowConfig

data_fetching.py - Step 0 Data Fetching
---------------------------------------
Functions:
  run_step0_fetch_and_aggregate(project_root, auto_fetch, stale_hours, verbose)
      -> bool (True if data fresh)
  check_data_freshness(file_path, threshold_hours)
      -> Tuple[is_fresh, hours_behind, last_timestamp]
  get_raw_8h_info(project_root)
      -> Dict with exists, row_count, last_timestamp, file_path

state_detection.py - Pipeline State Detection
---------------------------------------------
Classes:
  DataStatus            - Dataclass with raw_rows, merged_rows, etc.

Functions:
  get_data_status(project_root) -> DataStatus
  detect_new_data(project_root, pipeline_state, verbose)
      -> Tuple[new_data_detected, raw_rows]
  check_file_sync(project_root, filename, expected_rows, verbose)
      -> Tuple[is_current, current_rows]
  check_optimized_files(project_root, targets, horizons, expected_rows, verbose)
      -> bool (all files exist and current)

validation.py - Pipeline Validation
-----------------------------------
Classes:
  CausalityTestResult        - spike_test_passed, manual_verify_passed, etc.
  PipelineVerificationResult - all_passed, checks list, details dict

Functions:
  run_causality_test(verbose) -> CausalityTestResult
  run_pipeline_verification(project_root, verbose) -> PipelineVerificationResult
  verify_step1_features(project_root, verbose) -> Dict
  verify_step2_targets(project_root, verbose) -> Dict
  verify_step3_optimization(project_root, targets, horizons, verbose) -> Dict

l1_helpers.py - L1 Precomputation Helpers
-----------------------------------------
Functions:
  compute_feasible_iters(config_name, cfg, backtest_rows, max_timestamp)
      -> int (max possible iterations)
  check_config_status(config_name, cfg, expected_iters, expected_features)
      -> Dict with status, current_iters, current_features, needs_recompute
  print_rust_status() -> Dict[helper_name, has_rust]
  scan_config_status(configs, cfg, l1_rows, expected_features, global_end, verbose)
      -> Tuple[to_compute_list, to_skip_list]

================================================================================
ADDING NEW FUNCTIONALITY
================================================================================

To add a new constant:
  1. Add to config.py with type annotation
  2. Add to __all__ in this file
  3. Add to imports in this file

To add a new function:
  1. Add to appropriate module (data_fetching, state_detection, etc.)
  2. Add docstring with Args/Returns
  3. Export in module's section in this file
  4. Add to __all__

To add a new module:
  1. Create scripts/workflow/new_module.py
  2. Add import section in this file
  3. Add exports to __all__
  4. Update docstring above

================================================================================
"""

# Config exports
from .config import (
    ALL_HORIZONS,
    AUTO_FETCH_IF_STALE,
    EXPECTED_FEATURES,
    L1_CONFIG_MODE,
    L1_HELPERS,
    L1_ROWS,
    STALE_THRESHOLD_HOURS,
    WORKFLOW_HORIZONS,
    WORKFLOW_TARGETS,
    L2BacktestDefaults,
    WorkflowConfig,
    get_all_configs,
    get_all_optimization_metadata,
    get_configs_1bar,
    get_configs_reduced,
    get_project_root,
    get_workflow_config,
    get_workflow_configs,
    print_optimization_summary,
    read_optimization_metadata,
)

# Data fetching exports
from .data_fetching import (
    check_data_freshness,
    get_raw_8h_info,
    run_step0_fetch_and_aggregate,
)

# L1 helper exports
from .l1_helpers import (
    check_config_status,
    compute_feasible_iters,
    print_rust_status,
    scan_config_status,
)

# Metrics tracking exports
from .metrics_tracking import (
    QualityGateError,
    check_quality_degradation,
    check_step_quality,
    compute_optimization_metrics,
    compute_step_metrics,
    get_baseline_metrics,
    load_metrics_history,
    print_metrics_comparison,
    print_quality_summary,
    record_run_metrics,
    run_l1_quality_gate,
    run_quality_gate,
    snapshot_l1_historical,
    verify_l1_historical,
)

# State detection exports
from .state_detection import (
    DataStatus,
    check_file_sync,
    check_optimized_files,
    detect_new_data,
    get_data_status,
)

# Validation exports
from .validation import (
    CausalityTestResult,
    PipelineVerificationResult,
    run_causality_test,
    run_pipeline_verification,
    verify_step1_features,
    verify_step2_targets,
    verify_step3_optimization,
)

__all__ = [
    # Config
    "WORKFLOW_HORIZONS",
    "WORKFLOW_TARGETS",
    "ALL_HORIZONS",
    "AUTO_FETCH_IF_STALE",
    "STALE_THRESHOLD_HOURS",
    "L1_CONFIG_MODE",
    "L1_ROWS",
    "L1_HELPERS",
    "EXPECTED_FEATURES",
    "WorkflowConfig",
    "get_workflow_config",
    "get_workflow_configs",
    "get_configs_1bar",
    "get_configs_reduced",
    "get_all_configs",
    "get_project_root",
    "L2BacktestDefaults",
    "read_optimization_metadata",
    "get_all_optimization_metadata",
    "print_optimization_summary",
    # Data fetching
    "run_step0_fetch_and_aggregate",
    "check_data_freshness",
    "get_raw_8h_info",
    # State detection
    "detect_new_data",
    "get_data_status",
    "check_file_sync",
    "check_optimized_files",
    "DataStatus",
    # Validation
    "run_causality_test",
    "run_pipeline_verification",
    "verify_step1_features",
    "verify_step2_targets",
    "verify_step3_optimization",
    "CausalityTestResult",
    "PipelineVerificationResult",
    # L1 helpers
    "compute_feasible_iters",
    "check_config_status",
    "print_rust_status",
    "scan_config_status",
    # Metrics tracking
    "record_run_metrics",
    "load_metrics_history",
    "compute_optimization_metrics",
    "check_quality_degradation",
    "print_metrics_comparison",
    "get_baseline_metrics",
    # Quality gates
    "QualityGateError",
    "run_quality_gate",
    "check_step_quality",
    "compute_step_metrics",
    "print_quality_summary",
    # L1 historical consistency
    "snapshot_l1_historical",
    "verify_l1_historical",
    "run_l1_quality_gate",
]
