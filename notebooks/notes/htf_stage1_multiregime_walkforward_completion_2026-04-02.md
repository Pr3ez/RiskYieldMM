# HTF Stage-1 Multiregime Walk-Forward Completion 2026-04-02

## Scope

Full CatBoost Stage-1 walk-forward execution on latest HTF production data for:

- `8h/B`
- `8h/C`
- `24h/B`
- `24h/C`
- `7d/B`
- `7d/C`

Target:

- `1m / target_4class`

Runner:

- [htf_stage1_regime_family_walkforward.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_regime_family_walkforward.py)

## Completion Status

All six runs completed successfully.

Per-root progress artifacts show only `completed` statuses:

- `8h/B`: `500/500`
- `8h/C`: `500/500`
- `24h/B`: `500/500`
- `24h/C`: `500/500`
- `7d/B`: `170/170`
- `7d/C`: `170/170`

`7d` completed fewer steps because only `170` eligible prediction batches were available under the Stage-1 walk-forward constraints.

## Primary Artifacts

Launcher summary:

- [summary_20260402_113920.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_stage1_regime_family_walkforward/summary_20260402_113920.json)

Per-root run directories:

- [stage1_catboost_8h_b_live](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_live)
- [stage1_catboost_8h_c_live](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_c_live)
- [stage1_catboost_24h_b_live](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_24h_b_live)
- [stage1_catboost_24h_c_live](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_24h_c_live)
- [stage1_catboost_7d_b_live](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_7d_b_live)
- [stage1_catboost_7d_c_live](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_7d_c_live)

Per-root summaries:

- [run_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_live/run_summary.json)
- [run_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_c_live/run_summary.json)
- [run_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_24h_b_live/run_summary.json)
- [run_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_24h_c_live/run_summary.json)
- [run_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_7d_b_live/run_summary.json)
- [run_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_7d_c_live/run_summary.json)

## Batch Ranges

- `8h/B`: prediction batches `5170..5669`
- `8h/C`: prediction batches `5170..5669`
- `24h/B`: prediction batches `1391..1890`
- `24h/C`: prediction batches `1390..1889`
- `7d/B`: prediction batches `101..270`
- `7d/C`: prediction batches `101..270`

## Walk-Forward Metrics

### `8h/B`

- steps: `500`
- quality-pass steps: `112`
- quality-pass rate: `0.2240`
- mean winner accuracy: `0.516842`
- top winner combos:
  - `f2_v1_t3`: `74`
  - `f2_v2_t10`: `70`
  - `f2_v3_t9`: `66`

### `8h/C`

- steps: `500`
- quality-pass steps: `122`
- quality-pass rate: `0.2440`
- mean winner accuracy: `0.525758`
- top winner combos:
  - `f2_v2_t10`: `73`
  - `f2_v3_t9`: `69`
  - `f7_v1_t4`: `65`

### `24h/B`

- steps: `500`
- quality-pass steps: `126`
- quality-pass rate: `0.2520`
- mean winner accuracy: `0.523389`
- top winner combos:
  - `f2_v3_t9`: `110`
  - `f2_v2_t10`: `74`
  - `f2_v1_t3`: `68`

### `24h/C`

- steps: `500`
- quality-pass steps: `80`
- quality-pass rate: `0.1600`
- mean winner accuracy: `0.484883`
- top winner combos:
  - `f2_v3_t9`: `91`
  - `f2_v2_t10`: `72`
  - `f2_v1_t3`: `69`

### `7d/B`

- steps: `170`
- quality-pass steps: `72`
- quality-pass rate: `0.4235`
- mean winner accuracy: `0.624208`
- top winner combos:
  - `f2_v3_t9`: `46`
  - `f2_v2_t10`: `35`
  - `f2_v1_t3`: `26`

### `7d/C`

- steps: `170`
- quality-pass steps: `104`
- quality-pass rate: `0.6118`
- mean winner accuracy: `0.732283`
- top winner combos:
  - `f2_v1_t3`: `43`
  - `f2_v2_t10`: `35`
  - `f2_v3_t9`: `29`

## High-Level Read

On this Stage-1 walk-forward pass:

- strongest quality-pass rate: `7d/C`
- strongest mean winner accuracy: `7d/C`
- strongest `24h` root: `24h/B`
- `8h/C` slightly outperformed `8h/B` on both quality-pass rate and mean winner accuracy

This does **not** replace the earlier bounded benchmark directly; it is the real full walk-forward Stage-1 result on the current production HTF corpus.

## Notes

Two important implementation notes remain:

1. Stage-1 root-aware execution is now working and was used for this run.
2. `resume_mode=skip_completed` still appears to recompute an already-smoked first step in some cases, so Stage-1 resume semantics still need a separate audit.
