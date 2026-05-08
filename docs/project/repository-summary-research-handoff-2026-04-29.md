# RiskYieldMM Repository Summary And Research Handoff

Date: 2026-04-29
Scope: local repository audit for `/media/przem/linux_data/RiskYieldMM (Copy)`.

> Historical note
>
> This handoff predates the multi-asset branch. It describes the prior
> BTCUSDT/Bybit-focused HTF workflow. Current source-data and HTF materialization
> support `BTCUSDT`, `ETHUSDT`, `EURUSD`, `USDJPY`, `GC`, `CL`, `ES`, and `NQ`.
> Stage-1 and downstream analysis are still being updated for multi-asset
> target/context selection.

## Executive Summary

At the time of this 2026-04-29 audit, RiskYieldMM was a crypto perpetual
futures ML research system focused on Bybit BTCUSDT linear perpetual data. Since
then, the branch has added multi-asset source data and per-asset HTF
materialization. The Stage-1 and downstream analysis layer described here is
the legacy regime/family workflow.

The project is artifact-heavy. The local tree is about 151 GB:

- `data`: about 77 GB
- `test_output`: about 35 GB
- `backups`: about 29 GB
- `prediction_analysis`: about 8.4 GB

The important source/docs layer is much smaller and is concentrated in:

- `notebooks/htf_pythonscript.py`
- `scripts/feature_engineering/`
- `scripts/analysis/`
- `scripts/htf_backtest/catboost/`
- `scripts/target_models/`
- `riskyield_rust/src/`
- `docs/` and `notebooks/notes/`

## Source Of Truth At Audit Time

The production launcher at audit time was:

- `notebooks/htf_pythonscript.py`

The shared materialization logic at audit time was:

- `scripts/feature_engineering/htf_multiregime_pipeline.py`

The Stage-1 CatBoost walk-forward runner at audit time was:

- `scripts/analysis/htf_stage1_regime_family_walkforward.py`
- `scripts/htf_backtest/catboost/stage1_runner.py`

The target surface at audit time was:

- timeframe: `1m`
- target: `target_4class`
- model family: CatBoost
- roots: `8h/B`, `8h/C`, `24h/B`, `24h/C`, `7d/B`, `7d/C`

Older L2 target models, conformal prediction, notebooks, and archived scripts remain useful background, but they are not the current main HTF workflow.

## Repository Map

| Path | Role |
| --- | --- |
| `README.md` | Best high-level orientation. Already summarizes active workflow and review path. |
| `fetchingByBit/` | Bybit data fetch/update/quality pipeline plus local raw market data folders. |
| `scripts/feature_engineering/` | HTF data materialization, label kernels, optimizer, helper cache, feature validation. |
| `scripts/analysis/` | Offline audits, diagnostics, Stage-1 multi-regime runner, Stage-1-v2 selector audits. |
| `scripts/htf_backtest/` | Backtest runners and model-specific CatBoost/LightGBM tooling. |
| `scripts/htf_backtest/catboost/` | Current core Stage-1 CatBoost implementation, selector steps, reward/policy data. |
| `scripts/target_models/` | Older L2 model layer: target configs, models, helpers, conformal calibration, validation. |
| `riskyield_rust/` | Rust/PyO3 helper accelerators for Kalman, GARCH, EGARCH, CUSUM, OU, EVT, BOCPD, HMM. |
| `data/` | Local/generated datasets, HTF features, labels, helper outputs, Stage-1 runs. |
| `test_output/` | Generated audits, smoke outputs, diagnostics, Stage-1-v2 analysis products. |
| `prediction_analysis/` | Historical research scripts and output trees for ensemble/multitimeframe experiments. |
| `docs/` | Architecture, implementation plans, validation research, conformal docs, target redesign notes. |
| `notebooks/notes/` | Chronological research/implementation log. Very important for current context. |
| `Archive/` | Legacy implementations and backups. Useful for history, but not current source of truth. |
| `extensions/astra-workflow/` | VS Code extension project for Astra workflow tooling. Mostly separate from ML pipeline. |
| `.agents/skills/` | Local agent skills for audits, worklog, experiment ranking, ML run contracts. |

## Main Workflow

### 1. Bybit Data Ingestion

Path:

- `fetchingByBit/fetch_bybit_market_data.py`
- `fetchingByBit/update_data.py`
- `fetchingByBit/aggregate_to_8h.py`
- `fetchingByBit/data_quality_monitor.py`
- `fetchingByBit/gap_filler.py`

Purpose:

- Fetch Bybit BTCUSDT linear perpetual data from 2021-01-01 onward.
- Sources include OHLCV, funding, open interest, long/short ratio, mark price, index price, premium price.
- Maintain resumable fetch progress in `.fetch_progress.json`.
- Validate gaps, duplicates, nulls, continuity, and cross-source alignment.

Important research issue:

- Current Bybit API behavior, endpoint limits, retention, and schema stability must be rechecked before relying on new data refreshes.

### 2. Multi-Regime HTF Materialization

Main files:

- `notebooks/htf_pythonscript.py`
- `scripts/feature_engineering/htf_multiregime_pipeline.py`
- `scripts/feature_engineering/htf_shared_config.py`
- `scripts/feature_engineering/htf_kernels.py`
- `scripts/feature_engineering/htf_helper_cache.py`
- `scripts/feature_engineering/optimize_htf_features.py`

Regime/family design:

| Regime | Duration | Family B | Family C |
| --- | ---: | --- | --- |
| `8h` | 8 hours | base anchored | shifted by 4 hours |
| `24h` | 24 hours | base anchored | shifted by 12 hours |
| `7d` | 168 hours | base anchored | shifted by 84 hours |

Pipeline stages:

1. Build `1m` and `15m` combined HTF OHLCV batches.
2. Compute HTF feature batches.
3. Compute `15m` forward distance metrics.
4. Generate `1m` labels, mainly `target_4class`.
5. Optimize model-facing feature batches.
6. Materialize helper features from canonical helper cache.
7. Validate alignment, ranges, missingness, entry-window correctness, and helper readiness.

Model-facing roots at audit time:

| Root | Features | Labels | Stage-1 run id |
| --- | --- | --- | --- |
| `8h/B` | `data/htf_with_helpers` | `data/htf_4class_labels` | `stage1_catboost_8h_b_live` |
| `8h/C` | `data/htf_with_helpers_shift4h` | `data/htf_4class_labels_shift4h` | `stage1_catboost_8h_c_live` |
| `24h/B` | `data/htf_with_helpers_24h` | `data/htf_4class_labels_24h` | `stage1_catboost_24h_b_live` |
| `24h/C` | `data/htf_with_helpers_24h_shift12h` | `data/htf_4class_labels_24h_shift12h` | `stage1_catboost_24h_c_live` |
| `7d/B` | `data/htf_with_helpers_7d` | `data/htf_4class_labels_7d` | `stage1_catboost_7d_b_live` |
| `7d/C` | `data/htf_with_helpers_7d_shift84h` | `data/htf_4class_labels_7d_shift84h` | `stage1_catboost_7d_c_live` |

### 3. Current Labeling

Main file:

- `scripts/feature_engineering/htf_kernels.py`

Primary label:

- `target_4class`

Classes:

- `0`: `DOWN_BALANCED`
- `1`: `DOWN_EXPANSION`
- `2`: `UP_BALANCED`
- `3`: `UP_EXPANSION`
- `-1`: invalid/unresolved/outside entry window

The label uses forward distance metrics and risk/expansion logic. Labels are valid only inside the regime entry window:

- `8h`: first 4 hours
- `24h`: first 12 hours
- `7d`: first 84 hours

Research concern:

- The label is central to the whole project. The researcher should validate whether the thresholds, class definitions, and entry-window assumptions match the intended trading decision and whether they create class imbalance or ambiguous path behavior.

### 4. Stage-1 CatBoost Walk-Forward

Main files:

- `scripts/analysis/htf_stage1_regime_family_walkforward.py`
- `scripts/htf_backtest/catboost/stage1_runner.py`
- `scripts/htf_backtest/catboost/stage1_optimizer.py`
- `scripts/htf_backtest/catboost/stage1_selector_step.py`
- `scripts/htf_backtest/catboost/stage1_v2_contract.py`

Purpose:

- Generate leakage-safe walk-forward payloads for every configured combo.
- Persist raw fold validation predictions and prediction-batch predictions.
- Support offline combo selection, reward/policy datasets, and feature-pruning analysis.

Typical Stage-1 artifact path:

- `data/htf_backtest_results/{run_id}/catboost/1m/target_4class/batch_{pred_batch}/stage1/`

Important files per step:

- `stage1_step_summary.json`
- `stage1_combo_index.parquet`
- `stage1_fold_windows.parquet`
- `stage1_val_predictions.parquet`
- `stage1_pred_batch_predictions.parquet`
- `stage1_predecision_context.json`
- `stage1_predecision_context.parquet`
- `stage1_runtime_profile.json`

Current Stage-1 behavior from notes:

- Six roots are the main evaluation set.
- Current live search is effectively narrow: about 8 active action-key combos per step.
- Adaptive probing/promotion exists, but notes indicate it is effectively inactive in current live runs.
- Runtime is dominated by repeated CatBoost fold-CV training.

### 5. Causal Multiregime Method Analysis

Main file:

- `scripts/analysis/htf_causal_multiregime_method_analysis.py`

Purpose:

- Compare no-lookahead ensemble/post-processing methods over Stage-1 outputs.
- Methods include uniform argmax, all-agree filters, online hedge, diversity subset, per-class specialist, regime router, stacking, and discounted model averaging.

Important output:

- `test_output/htf_causal_multiregime_method_analysis/`

Notable documented result from `notebooks/notes/htf_causal_multiregime_method_analysis_2026-04-02.md`:

- `7d/C` was the strongest root in that run under clean causal evaluation, with full-coverage `stacking_meta` directional accuracy around `0.648`.
- `8h/C` showed clean lift with discounted model averaging around `0.544`.
- Some methods improve only with low row coverage, which should be treated as abstention rather than full replacement.

### 6. Diagnostics And Feature Importance

Main files:

- `scripts/analysis/htf_walkforward_diagnostics.py`
- `scripts/htf_backtest/catboost/stage1_step2.py`
- `scripts/analysis/htf_stage1_v2_*`

Purpose:

- Build root profiles, cross-root summaries, base model diagnostics, causal method refreshes, feature-quality joins, and Step-2 feature pruning/importance.

Stage-1-v2 already records substantial data:

- combo metrics
- feature importance rows
- selected feature masks
- baseline vs selected comparisons
- fixed-policy registry and replay artifacts

Important current gap:

- A 2026-04-22 note says exact per-fold train/validation batch membership for each combo-step is not explicitly persisted in Stage-1-v2. It can be reconstructed, but for causality audits it should probably be persisted directly.

### 7. Older L2 Target Model Layer

Main files:

- `scripts/target_models/pipeline.py`
- `scripts/target_models/models/`
- `scripts/target_models/helpers/`
- `scripts/target_models/calibration/`
- `scripts/target_models/validation/`
- `scripts/workflow/config.py`

Role:

- Older multi-target L2 modeling system with CatBoost/LightGBM/linear/LSTM-style components, helper features, optimization, validation, and conformal prediction.

Status:

- Useful engineering evidence and reference material.
- Not the current main HTF workflow.
- Several docs identify TODOs around triple-barrier labels, meta-labeling, fractional differentiation, dynamic weights, config sync, and preprocessing.

Conformal prediction appears implemented and documented under:

- `docs/conformal/`
- `scripts/target_models/calibration/`

Documented coverage:

- regression around 90.7 to 96.3 percent against 90 percent target
- binary classification around 91.5 percent
- multiclass around 89 to 93 percent

### 8. Rust Helper Acceleration

Main files:

- `riskyield_rust/Cargo.toml`
- `riskyield_rust/src/lib.rs`
- `riskyield_rust/src/*.rs`

Purpose:

- PyO3/maturin extension for high-performance helper calculations.
- Modules include Kalman, GARCH, EGARCH, CUSUM, Ornstein-Uhlenbeck, EVT/POT, BOCPD, and HMM.

Research concern:

- The mathematical definitions and streaming-state behavior should be independently checked for causality, numerical stability, and consistency with Python fallback/helper consumers.

## Key Docs To Give The Researcher

Start with:

- `README.md`
- `docs/htf/stage1-logic.md`
- `docs/htf/stage1-artifacts.md`
- `docs/htf/target-labeling-logic.md`
- `notebooks/notes/htf_causal_multiregime_method_analysis_2026-04-02.md`
- `notebooks/notes/htf_stage1_current_behavior_and_improvement_plan_2026-04-19.md`
- `notebooks/notes/htf_stage1_v2_full_diagnostic_inventory_2026-04-22.md`
- `notebooks/notes/htf_complete_batch_readiness_audit_2026-04-13.md`
- `docs/conformal/README.md`
- `docs/plans/implementation-status.md`
- `docs/plans/backtest-cleanup-todo.md`
- `docs/preprocessing/MASTER_TODO.md`
- `docs/target-redesign/multi-label-targets-research.md`

## Important Risks And Gaps Found

### P0: Hardcoded API Credentials In Archive

`Archive/previous_work/position_manage/bybitmodel.py` contains hardcoded Bybit API key/secret strings. Do not reuse those credentials. They should be revoked/rotated immediately, and repository history should be cleaned before public sharing.

### P0: Reproducibility Is Not Fully Packaged

`pyproject.toml` defines project metadata and Ruff settings but does not declare the full runtime dependency set. README gives manual install commands. There is no detected `requirements.txt`, `environment.yml`, lockfile for Python, or CI workflow.

Researcher should produce:

- exact environment spec
- Python/CUDA/CatBoost/Polars/PyArrow versions
- Rust/maturin build instructions
- GPU assumptions
- reproducible smoke-test commands

### P0: Large Local Artifacts Dominate The Repo

Local tree is about 151 GB. Git tracks thousands of files, while `.gitignore` now ignores generated data going forward. Historical large files may already be present.

Researcher should decide:

- what artifacts are canonical and should be preserved
- what belongs in Git LFS, DVC, external storage, or should be regenerated
- what can be deleted or archived outside the repo

### P0: Current Branch Is Behind Remote

`git status --short --branch` reports `main...origin/main [behind 1]`.

Researcher should check the remote commit before major work so the handoff is not based on a stale branch.

### P1: Hardcoded Local Paths

Several scripts and notebooks hardcode `/media/przem/linux_data/RiskYieldMM (Copy)`, especially in notebooks and Stage-1 helper scripts. The production launcher resolves root dynamically, but other paths remain local-machine-specific.

Researcher should identify which entrypoints must be portable and recommend a config/env based root resolver.

### P1: Test Coverage Does Not Cover The Active HTF Core Enough

Existing tests cover analysis utilities, PurgedKFold, optimizers, registry/model helper behavior, and ICIR selection. I did not find direct unit tests for the current multi-regime HTF pipeline, Stage-1 artifact contracts, Stage-1-v2 fold membership, or helper-cache materialization.

Researcher should propose:

- small synthetic HTF fixture tests
- artifact contract tests
- no-lookahead tests for labels/features/helpers
- Stage-1 resume/skip/migration tests
- row alignment tests across features/labels/helpers

### P1: Known HTF Feature Null/Completeness Issues

`notebooks/notes/htf_complete_batch_readiness_audit_2026-04-13.md` says remaining null-feature blockers on complete batches were narrowed to 10 features, including distance, candlestick zero-range, and long/short-derived features.

Researcher should verify whether these are fixed in current data and whether model-facing batches are fit-ready.

### P1: Stage-1 Runtime And Selector Complexity

Current notes say Stage-1 is expensive because of repeated fold-CV training, while adaptive probing/promotion is effectively inactive. Quality unresolved rates are high, especially in 24h and 7d roots.

Researcher should study:

- whether cache reuse can be improved without changing results
- whether inactive probe code should be fixed or removed from routine runs
- whether quality thresholds are realistic
- whether dynamic model averaging/loss-discounting is the right selector layer

### P1: Stage-1-v2 Missing Explicit Fold Membership

The 2026-04-22 diagnostic inventory says exact per-fold train/validation batch membership is not explicitly persisted in Stage-1-v2. This is a causality/auditability gap.

Researcher should specify the exact artifact schema needed to persist fold membership.

### P1: Target Design Still Needs External Validation

Docs propose multi-label/path-aware targets, including trend vs breakout vs mean-revert vs ranging. Current `target_4class` captures direction plus expansion/risk, but may not distinguish price path sufficiently.

Researcher should review:

- `target_4class` definitions and thresholds
- path labels using 15m intrabar data
- Kaufman efficiency ratio, Hurst/DFA, V-shape/mean-reversion detection
- triple-barrier and event-labeling alternatives
- class balance and economic utility of each target

### P2: Older L2 System Has Documented TODOs

Docs identify older-layer TODOs:

- triple-barrier labels
- sample uniqueness
- meta-labeling
- fractional differentiation
- adaptive ensemble weights
- config synchronization between `L2BacktestDefaults` and `SyncBacktestConfig`
- incomplete preprocessing workflow

Researcher should decide which of these still matters for the active HTF path.

### P2: Repo Hygiene Issues

Cleanup applied on 2026-04-29:

- removed tracked stray root files: `''`, `.codex`, `a.drawio copy.svg`, and `test_ruff.py`
- removed tracked generated CatBoost training output under `catboost_info/`
- moved `a.drawio.svg` to `docs/diagrams/riskyieldmm_workflow.drawio.svg`
- moved root-level research reports to `docs/research/`
- archived `todobkup.md` under `Archive/root_cleanup_20260429/`
- removed local generated logs and caches from the working tree

Remaining local-only hygiene notes:

- `.gitignore` now covers `.ruff_cache/` and `catboost_info/`
- `cv_tmp/` private files present locally but ignored
- `extensions/astra-workflow/node_modules/` exists locally
- no detected CI workflow

## Research Questions To Send Out

### A. Data And Market Microstructure

1. Are Bybit BTCUSDT linear perpetual OHLCV, open interest, funding, mark/index/premium, and long/short ratio endpoints still stable as of 2026-04-29?
2. What are the current endpoint retention windows, rate limits, pagination limits, and schema differences?
3. Is local 4h-to-8h aggregation still the correct approach, or should 12h/native intervals be used differently?
4. Are funding timestamps and 8h HTF batch boundaries aligned correctly under UTC and Bybit conventions?
5. What source gaps or revisions exist in Bybit historical auxiliary data, especially long/short ratio?

### B. Label And Target Methodology

1. Is `target_4class` a defensible target for the intended trading decision?
2. Should class labels be path-aware instead of only direction plus expansion/risk?
3. Which target design best matches expected execution: entry-only window, hold-to-end, dynamic exit, or barrier-based?
4. What thresholds should be volatility-normalized, asset-specific, or regime-specific?
5. How should invalid rows (`-1`) and unresolved outcomes be handled in training and evaluation?

### C. Leakage And Validation

1. Does every HTF feature/helper use only data available at prediction time?
2. Does helper-cache warmup/refit logic avoid using future information across batch boundaries?
3. Are Stage-1 train, validation, calibration, and prediction windows causally ordered for every action key?
4. Are current artifact schemas sufficient to prove no lookahead, or should exact fold membership be persisted?
5. Are any model-selection policies selecting from final prediction-batch outcomes rather than predecision context?

### D. Selector And Ensemble Research

1. For combo selection, should the baseline be loss-discounted model averaging, dynamic model averaging, online weighted majority, or a learned meta-selector?
2. Which loss should drive selection: filtered cross-direction error, directional accuracy, macro F1, Brier/log-loss, or a weighted blend?
3. How should abstention/coverage tradeoffs be evaluated and reported?
4. Can pairwise disagreement, confidence, entropy, regime features, and recent errors improve selector decisions without leakage?
5. How should root-level methods be combined across `8h`, `24h`, and `7d` families?

### E. Statistical And Economic Evaluation

1. What is the right null model for directional accuracy in this class distribution?
2. Are reported lifts statistically significant after multiple testing across roots, methods, and configs?
3. Which metrics translate to trading utility after fees, slippage, funding, and position sizing?
4. How should confidence intervals, bootstrap, block bootstrap, or conformal coverage be applied under overlapping labels?
5. Should evaluation include PnL-style backtest metrics or stay at forecast-quality metrics first?

### F. Engineering And Reproducibility

1. What minimal environment spec reproduces the active HTF path?
2. Which generated artifacts are required for a reviewer and which should move to DVC/Git LFS/external storage?
3. What are the mandatory smoke tests before any full run?
4. What is the correct CI subset for source-only checks?
5. How should local absolute paths be replaced by project-root config?

### G. Security And Publication

1. Which credentials were exposed in archive/history, and have they been revoked?
2. Should repository history be rewritten before public sharing?
3. Are personal documents, certificates, or logs accidentally tracked?
4. Are generated logs free of secrets and account identifiers?
5. What public/private split should exist for public sharing?

## Recommended Research Deliverables

Ask the researcher for these outputs:

1. `data_source_currentness_report.md`
   - Bybit API current endpoints, retention, rate limits, timestamp conventions, and known gaps.

2. `target_labeling_review.md`
   - Assessment of `target_4class`, path-aware labels, triple-barrier/event alternatives, and recommended target contract.

3. `leakage_audit_plan.md`
   - Concrete tests and artifact checks to prove no lookahead in features, helpers, labels, Stage-1, and selectors.

4. `selector_method_recommendation.md`
   - Literature-backed selector design, metric choice, loss-discounting/DMA baseline, and experiment plan.

5. `reproducibility_and_cleanup_plan.md`
   - Dependency spec, CI smoke tests, artifact storage policy, path portability, and secret cleanup steps.

## Suggested Next Implementation After Research

1. Rotate/revoke archived Bybit credentials and clean history/public copy.
2. Add an environment spec and one reproducible smoke path.
3. Add HTF synthetic fixture tests for labels, helper alignment, and Stage-1 artifact contracts.
4. Persist exact Stage-1-v2 fold train/validation membership.
5. Decide whether to fix or disable inactive adaptive probing.
6. Run a target-labeling review before adding more modeling complexity.
7. Implement one clean dynamic selector baseline driven by the chosen loss.
