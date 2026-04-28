# HTF Stage-1-v2 Foundation Slice 1

Date: 2026-04-20
Tracking:
- Linear: `RIS-199`

## Scope

First implementation slice for `Stage-1-v2`.

This slice does not implement nested combo-specific feature selection yet.
It implements the parity-safe foundation required before that heavier logic can be added.

## Implemented

### 1. Stage-1-v2 contract module

Added:
- [stage1_v2_contract.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_v2_contract.py)

Provides:
- stage version normalization
- v2 execution mode normalization
- v2 selector config validation
- v2 artifact contract version
- root-level and step-level expected artifact names

### 2. Reusable selector kernel

Added:
- [stage1_selector_kernel.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_selector_kernel.py)

Extracted shared logic from Step-2:
- metrics
- combo ranking helpers
- SHAP selector helpers
- CatBoost fit/predict helpers
- selected-feature extraction helpers

### 3. Step-2 rewired to use selector kernel

Updated:
- [stage1_step2.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_step2.py)

Effect:
- current Step-2 behavior remains the same
- shared logic now lives in a reusable module that Stage-1-v2 can call later

### 4. Stage-1 runner understands v1 vs v2

Updated:
- [stage1_runner.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_runner.py)

Added:
- `stage1_version`
- `stage1_v2_selector_config`
- v2 metadata persisted in:
  - `run_config.json`
  - `run_summary.json`
  - `stage1_run_state.json`
- root-level `stage1_v2_artifact_contract.json`

Current v2 behavior:
- `execution_mode=parity` only
- nested selector mode is intentionally not implemented yet
- if requested, runner raises `NotImplementedError`

### 5. Launcher wiring for v2

Updated:
- [htf_stage1_regime_family_walkforward.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_regime_family_walkforward.py)

Added:
- `--stage1-version v1|v2`
- `--stage1-v2-execution-mode parity|nested_selector`
- automatic v2 run ids like:
  - `stage1_catboost_8h_b_v2_live`

## Verified

### Compile

- `python -m py_compile scripts/analysis/htf_stage1_regime_family_walkforward.py scripts/htf_backtest/catboost/stage1_runner.py scripts/htf_backtest/catboost/stage1_step2.py scripts/htf_backtest/catboost/stage1_selector_kernel.py scripts/htf_backtest/catboost/stage1_v2_contract.py`

### Plan-only launcher

- v1 plan-only succeeded
- v2 plan-only succeeded and resolved v2 run id correctly

### One-step v2 parity smoke

Executed:
- `8h/B`
- `n_steps=1`
- `runtime_mode=routine`
- `stage1_version=v2`
- `stage1_v2_execution_mode=parity`

Observed output:
- [stage1_catboost_8h_b_v2_live](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live)
- `run_config.json` contains:
  - `mode=stage1_isolated_v2`
  - `stage1_version=v2`
  - `stage1_v2_artifact_contract_version`
  - `stage1_v2_selector_config`
- [stage1_v2_artifact_contract.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_artifact_contract.json) exists

## What Is Still Missing

Not implemented yet:
- nested per-combo feature selection inside Stage-1
- v2 step artifacts like:
  - `stage1_v2_combo_metrics.parquet`
  - `stage1_v2_feature_importance_steps.parquet`
  - `stage1_v2_selected_features.json`
- winner choice on selected-feature results
- diagnostics simplification based on v2-native artifacts

## Next Slice

1. define code-facing v2 artifact writers
2. extract selector execution path from Step-2 into a callable kernel
3. add `parity` branch output writing
4. then implement `nested_selector` for one-root smoke validation
