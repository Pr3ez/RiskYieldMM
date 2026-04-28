# HTF Walk-Forward Workflow Audit - 2026-04-18

## Scope

Trace the current production HTF workflow from saved production data through Stage-1 walk-forward outputs, Stage-1 Step-2 feature-pruning/importance analysis, causal ensemble analysis, and final evaluation artifacts.

## Source Of Truth

- Production HTF entrypoint: `notebooks/htf_pythonscript.py`
- Stage-1 notebook: `notebooks/htf_stage1.py`
- Stage-1 runner: `scripts/htf_backtest/catboost/stage1_runner.py`
- Stage-1 Step-2: `scripts/htf_backtest/catboost/stage1_step2.py`
- Latest causal analysis run: `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/htf_causal_multiregime_method_analysis/20260416_140508`
- Machine-readable manifest: `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/htf_walkforward_diagnostics/20260418_074215/workflow_manifest.json`

## Root Summary

### 24h/B

- Stage-1 eval batch range: `1511..1890` (`n=378`)
- Evaluated rows: `272160`
- Best full-coverage method: `hedge_online` / `eta=0.5_loss=nll`
- Best full-coverage directional accuracy: `0.5228909465020576`
- Best reduced-coverage method: `all_agree_class` / `direct`
- Direct baseline directional accuracy: `0.4984751616696061`
- Incomplete combo batches filtered: `2`

### 24h/C

- Stage-1 eval batch range: `1510..1889` (`n=380`)
- Evaluated rows: `273600`
- Best full-coverage method: `diversity_subset` / `subset=4_alpha=0.65_pow=1.0`
- Best full-coverage directional accuracy: `0.5253947368421052`
- Best reduced-coverage method: `diversity_subset` / `subset=4_alpha=0.65_pow=1.0`
- Direct baseline directional accuracy: `0.5219480994152047`
- Incomplete combo batches filtered: `0`

### 7d/B

- Stage-1 eval batch range: `221..270` (`n=50`)
- Evaluated rows: `252000`
- Best full-coverage method: `stacking_meta` / `c=0.5_iter=120`
- Best full-coverage directional accuracy: `0.5125277777777778`
- Best reduced-coverage method: `stacking_meta` / `c=0.5_iter=120`
- Direct baseline directional accuracy: `0.4629920634920635`
- Incomplete combo batches filtered: `0`

### 7d/C

- Stage-1 eval batch range: `223..270` (`n=48`)
- Evaluated rows: `241920`
- Best full-coverage method: `stacking_meta` / `c=0.5_iter=120`
- Best full-coverage directional accuracy: `0.5845072751322752`
- Best reduced-coverage method: `all_agree_direction` / `direct`
- Direct baseline directional accuracy: `0.5409556878306878`
- Incomplete combo batches filtered: `2`

### 8h/B

- Stage-1 eval batch range: `5290..5669` (`n=380`)
- Evaluated rows: `91200`
- Best full-coverage method: `hedge_online` / `eta=0.5_loss=nll`
- Best full-coverage directional accuracy: `0.5207894736842106`
- Best reduced-coverage method: `all_agree_direction` / `direct`
- Direct baseline directional accuracy: `0.5092543859649122`
- Incomplete combo batches filtered: `0`

### 8h/C

- Stage-1 eval batch range: `5290..5669` (`n=380`)
- Evaluated rows: `91200`
- Best full-coverage method: `hedge_online` / `eta=0.5_loss=nll`
- Best full-coverage directional accuracy: `0.5239254385964912`
- Best reduced-coverage method: `all_agree_class` / `direct`
- Direct baseline directional accuracy: `0.5030592105263157`
- Incomplete combo batches filtered: `0`
