# Research Reports

These reports are dated research/context documents. Use the root `README.md`,
`CHANGELOG.md`, and `docs/plans/htf_multi_asset_update_plan_2026-05-07.md` for
the current multi-asset implementation status.

| Document | Purpose |
|---|---|
| [`deep-research-report.md`](deep-research-report.md) | Repository analytical report |
| [`advanced-trading-strategies-research.md`](advanced-trading-strategies-research.md) | Advanced trading strategy research |
| [`backtest-improvements-research.md`](backtest-improvements-research.md) | Backtest improvement research |
| [`astra-consciousness-research.md`](astra-consciousness-research.md) | Astra research summary |
| [`supply-demand-pressure-research.md`](supply-demand-pressure-research.md) | Supply/demand pressure proxies across stocks and crypto |
| [`codex-skills-time-series-ml-report.md`](codex-skills-time-series-ml-report.md) | Codex skills/time-series ML report |
| [`stage1-label-anomaly-8h-b-research-brief-2026-05-20.md`](stage1-label-anomaly-8h-b-research-brief-2026-05-20.md) | Historical Stage-1 label-anomaly research brief, original 8h/B guardrail, BTCUSDT pilot evidence, and PyTorch blocker |
| [`stage1-label-anomaly-implementation-reference-2026-05-20.md`](stage1-label-anomaly-implementation-reference-2026-05-20.md) | Implementation reference for cleaned 4-class, Confident-Learning-style diagnostics, matrix gating, ES/GC follow-up, and test requirements |
| [`stage1-label-anomaly-8h-b-diagnostics-2026-05-20.md`](stage1-label-anomaly-8h-b-diagnostics-2026-05-20.md) | Current resume document for completed representative 8h/B CatBoost anomaly diagnostics, ES/GC sweep, direction-threshold diagnostic, and blockers |
| [`RiskYieldMM_Stage1_TripleBarrier_Anomaly_Labeling_Document.md`](RiskYieldMM_Stage1_TripleBarrier_Anomaly_Labeling_Document.md) | Triple-barrier/anomaly target research brief, including `tb_atr_wide_v2` rationale and pre-fix 250-step diagnostic context |
| [`tb-target-survey-8h-b-btcusdt-stage1-smoke-2026-05-21.md`](tb-target-survey-8h-b-btcusdt-stage1-smoke-2026-05-21.md) | BTCUSDT `8h/B` two-step target-survey smoke and label-sanity summary |
| [`tb-target-survey-8h-b-btcusdt-comparison-2026-05-26.md`](tb-target-survey-8h-b-btcusdt-comparison-2026-05-26.md) | Pre-sparse-fix BTCUSDT `tb_atr_wide_v2` comparison report; use as diagnostic history until rerun under sparse-aware Stage-1 windows |
| [`tb-target-survey-8h-b-btcusdt-comparison-2026-05-27.md`](tb-target-survey-8h-b-btcusdt-comparison-2026-05-27.md) | Fair sparse-aware 250-step BTCUSDT `8h/B` legacy-vs-`tb_atr_wide_v2` comparison and non-promotion decision |
| [`reg-distance-target-sanity-distance_horizon_vol_v2-8h-b-btcusdt-2026-05-28.md`](reg-distance-target-sanity-distance_horizon_vol_v2-8h-b-btcusdt-2026-05-28.md) | BTCUSDT `8h/B` sanity report for corrected horizon-volatility distance regression targets |
| [`reg-distance-target-validation-distance_horizon_vol_v2-8h-b-btcusdt-2026-05-28.md`](reg-distance-target-validation-distance_horizon_vol_v2-8h-b-btcusdt-2026-05-28.md) | Full-row validation of all four BTCUSDT `8h/B` horizon-volatility distance targets against source 15m label windows |
| [`reg-distance-target-walkforward-smoke-2026-05-28.md`](reg-distance-target-walkforward-smoke-2026-05-28.md) | Sparse-aware `CatBoostRegressor` smoke history for BTCUSDT `8h/B` distance targets, including the corrected v2 wiring checks |
| [`market-trend-regime-detection-report.md`](market-trend-regime-detection-report.md) | Market trend and regime detection report |
| [`engineering-macroeconomic-features-8h-models.pdf`](engineering-macroeconomic-features-8h-models.pdf) | Macroeconomic feature-engineering reference PDF |

## Analyst and trading-system redesign, July 2026

These documents cover the local Analyst application, causal replay and paper
trading, indicator research, and the current prediction-system redesign. The
numbered deep-research reports are preserved as supplied research inputs; the
diagnosis report records where their recommendations were accepted, narrowed,
or rejected against repository evidence.

| Document | Purpose |
|---|---|
| [`meta_model_analyst_indicator_research_2026-07-10.md`](meta_model_analyst_indicator_research_2026-07-10.md) | Initial CUSUM, EWMA, regime, and visualization research for the Analyst |
| [`background_live_data_and_forward_paper_2026-07-11.md`](background_live_data_and_forward_paper_2026-07-11.md) | Live-data ingestion and forward-paper architecture research |
| [`candle_construction_and_live_minute_replay_2026-07-11.md`](candle_construction_and_live_minute_replay_2026-07-11.md) | Completed-candle construction and causal one-minute replay rules |
| [`meta_model_analyst_next_feature_research_2026-07-12.md`](meta_model_analyst_next_feature_research_2026-07-12.md) | Market-context feature-family research and selection |
| [`professional_paper_replay_execution_contract_2026-07-12.md`](professional_paper_replay_execution_contract_2026-07-12.md) | Professional replay and paper-execution contract |
| [`indicator_driven_trade_policy_research_2026-07-12.md`](indicator_driven_trade_policy_research_2026-07-12.md) | Entry, stop, target, exit, and risk-policy research |
| [`cusum_meta_label_trade_filter_research_2026-07-13.md`](cusum_meta_label_trade_filter_research_2026-07-13.md) | CUSUM meta-label target, evaluation, and deployment boundaries |
| [`deep-research-report (8).md`](deep-research-report%20%288%29.md) | User-supplied starting research report 8; not an implementation specification |
| [`deep-research-report (9).md`](deep-research-report%20%289%29.md) | User-supplied starting research report 9; not an implementation specification |
| [`trading_prediction_system_diagnosis_and_redesign_2026-07-14.md`](trading_prediction_system_diagnosis_and_redesign_2026-07-14.md) | Evidence-backed end-to-end diagnosis, target architecture, experiment plan, and implementation roadmap |
