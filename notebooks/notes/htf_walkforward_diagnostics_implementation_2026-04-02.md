# HTF Walk-Forward Diagnostics Implementation - 2026-04-02

## What Was Implemented

### New analysis runner

- [htf_walkforward_diagnostics.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_walkforward_diagnostics.py)

The runner now supports:

- current six HTF roots:
  - `8h/B`
  - `8h/C`
  - `24h/B`
  - `24h/C`
  - `7d/B`
  - `7d/C`
- workflow manifest generation from production HTF -> Stage-1 -> causal ensemble artifacts
- root profiles from existing artifacts
- cross-root summary tables
- causal-method comparison refresh
- base-model diagnostics for winner-dominant and near-winner action keys
- root filtering with `--roots`
- phased execution with:
  - `audit`
  - `winner_only`
  - `root_topk`
- multiple feature-importance types via:
  - `--feature-importance-types`

### Step-2 scope extension

- [stage1_step2.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_step2.py)

Added support for:

- root-aware top-k action-key selection
- per-root artifact exports:
  - action-key ranking
  - baseline-vs-filtered summary
  - feature-importance stability
  - feature-noise summary
  - top-features-by-combo

### Step-2 robustness fix

Also fixed a real replay bug in Step-2:

- CatBoost `select_features()` could crash when the validation fold contained a class missing from that fold’s training set
- Step-2 now falls back from `train + eval` selection to `train_only` selection for that fold when needed
- this keeps the replay causal and prevents the whole analysis from dying on sparse fold class coverage

## Completed Today

### Phase A completed

Canonical Phase A outputs:

- [workflow note](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_walkforward_workflow_audit_2026-04-02.md)
- [research brief](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_catboost_research_brief_2026-04-02.md)
- [workflow_manifest.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_walkforward_diagnostics/20260402_181239/workflow_manifest.json)
- [root_profiles.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_walkforward_diagnostics/20260402_181239/root_profiles.csv)
- [cross_root_summary.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_walkforward_diagnostics/20260402_181239/cross_root_summary.csv)
- [causal_method_refresh.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_walkforward_diagnostics/20260402_181239/causal_method_refresh.csv)
- [base_model_diagnostics.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_walkforward_diagnostics/20260402_181239/base_model_diagnostics.csv)
- [recommendations.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_walkforward_diagnostics/20260402_181239/recommendations.csv)

### Phase B/C execution path validated

Validated on a real Step-2 smoke replay:

- root: `8h/B`
- scope: `winner_only`
- importance type: `PredictionValuesChange`

Result:

- the Step-2 pipeline runs on the new runner path
- the unseen-class selector crash was found and fixed
- the replay continued correctly after the fix

## What Is Still Heavy / Not Finished In This Pass

Full Phase B and C are code-ready, but they are expensive.

Observed from the live `8h/B` winner-only smoke:

- first `10 / 500` steps took about `5.1m`
- rough ETA for that one root / one scope / one importance type was about `248m`

That means:

- the full six-root Phase B/C sweep is a multi-hour to multi-day job
- it should be launched intentionally, not casually during interactive analysis

## Recommended Launch Order

### Phase B: winner-only

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  scripts/analysis/htf_walkforward_diagnostics.py \
  --phases winner_only \
  --feature-importance-types PredictionValuesChange,LossFunctionChange \
  --output-dir test_output/htf_walkforward_diagnostics
```

### Phase C: root top-3

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  scripts/analysis/htf_walkforward_diagnostics.py \
  --phases root_topk \
  --feature-importance-types PredictionValuesChange,LossFunctionChange \
  --output-dir test_output/htf_walkforward_diagnostics
```

### Safer staged launch

If runtime needs to be controlled, launch in this order:

1. `7d/C`
2. `8h/C`
3. `24h/C`
4. `7d/B`
5. `8h/B`
6. `24h/B`

Example:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  scripts/analysis/htf_walkforward_diagnostics.py \
  --roots 7d/C \
  --phases winner_only,root_topk \
  --feature-importance-types PredictionValuesChange,LossFunctionChange \
  --output-dir test_output/htf_walkforward_diagnostics
```

## Immediate Takeaways From Phase A

- `7d/C` remains the strongest current root under the causal full-coverage comparison
- `24h/C` has no full-coverage gain over its direct baseline, so more ensemble complexity is not the first priority there
- the weakest current winner-quality-pass roots are:
  - `24h/B`
  - `24h/C`
  - `8h/B`
  - `8h/C`
- this supports the next analysis order:
  - complete Step-2 importance first
  - then do targeted parameter studies, starting with `7d/C`, `8h/C`, `24h/C`
