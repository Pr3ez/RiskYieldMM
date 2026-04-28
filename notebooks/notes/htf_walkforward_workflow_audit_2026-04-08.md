# HTF Walk-Forward Workflow Audit - 2026-04-08

## Scope

Trace the current production HTF workflow from saved production data through Stage-1 walk-forward outputs, Stage-1 Step-2 feature-pruning/importance analysis, causal ensemble analysis, and final evaluation artifacts.

## Source Of Truth

- Production HTF entrypoint: `notebooks/htf_pythonscript.py`
- Stage-1 notebook: `notebooks/htf_stage1.py`
- Stage-1 runner: `scripts/htf_backtest/catboost/stage1_runner.py`
- Stage-1 Step-2: `scripts/htf_backtest/catboost/stage1_step2.py`
- Latest causal analysis run: `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/htf_causal_multiregime_method_analysis/20260402_170806`
- Machine-readable manifest: `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/htf_walkforward_diagnostics/20260408_132339/workflow_manifest.json`

## Root Summary

### 24h/B

- Stage-1 eval batch range: `1511..1890` (`n=378`)
- Evaluated rows: `272160`
- Best full-coverage method: `stacking_meta` / `c=2.0_iter=180`
- Best full-coverage directional accuracy: `0.5096340388007055`
- Best reduced-coverage method: `stacking_meta` / `c=2.0_iter=180`
- Direct baseline directional accuracy: `0.4913800705467372`
- Incomplete combo batches filtered: `2`

### 24h/C

- Stage-1 eval batch range: `1510..1889` (`n=380`)
- Evaluated rows: `273600`
- Best full-coverage method: `uniform_direction_sum` / `direct`
- Best full-coverage directional accuracy: `0.5216301169590644`
- Best reduced-coverage method: `uniform_direction_sum` / `direct`
- Direct baseline directional accuracy: `0.5216301169590644`
- Incomplete combo batches filtered: `0`

### 7d/B

- Stage-1 eval batch range: `221..270` (`n=50`)
- Evaluated rows: `252000`
- Best full-coverage method: `diversity_subset` / `subset=4_alpha=0.55_pow=1.2`
- Best full-coverage directional accuracy: `0.5176468253968254`
- Best reduced-coverage method: `diversity_subset` / `subset=4_alpha=0.55_pow=1.2`
- Direct baseline directional accuracy: `0.5041785714285715`
- Incomplete combo batches filtered: `0`

### 7d/C

- Stage-1 eval batch range: `223..270` (`n=48`)
- Evaluated rows: `241920`
- Best full-coverage method: `stacking_meta` / `c=0.5_iter=120`
- Best full-coverage directional accuracy: `0.6480696097883598`
- Best reduced-coverage method: `stacking_meta` / `c=0.5_iter=120`
- Direct baseline directional accuracy: `0.6056464947089947`
- Incomplete combo batches filtered: `2`
