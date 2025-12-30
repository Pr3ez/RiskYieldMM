# MAPIE/ACI Integration - Validation-First Approach

- [-] p1-research-mapie: Phase 1.1: Study MAPIE API - Read docs for MapieClassifier, MapieTimeSeriesRegressor. Answer: min cal samples? cv=prefit? methods available? partial_fit? memory needs? 🔴
  _DELIVERABLE: Research notes with all questions answered. Cannot proceed to Phase 2 without this._
- [ ] p1-research-aci: Phase 1.2: Study ACI paper (Zaffran 2022, arXiv:2202.07282). Answer: gamma values for financial data? samples to stabilize? multi-target handling? 🔴
  _DELIVERABLE: ACI algorithm summary + recommended gamma range_
- [ ] p1-doc-pipeline: Phase 1.3: Document current pipeline gaps - Map where calibration happens, identify cal window sizes, document ensemble output format 🔴
  _DELIVERABLE: Gap analysis document. KNOWN ISSUE: Current cal ~20 samples, MAPIE needs 100+_
- [ ] p2-install: Phase 2.1: Install MAPIE & basic import test. pip install mapie. Verify imports work. Check version. 🔴
  _PASS: imports work, version >= 0.8. FAIL: install issues → resolve before continuing_
- [ ] p2-catboost-test: Phase 2.2: CatBoost compatibility test. Load direction_1bar, fit CatBoostClassifier, wrap in MapieClassifier(cv=prefit), verify prediction sets. 🔴
  _PASS: no errors, correct shape, coverage ~90%. FAIL: investigate sklearn API issues_
- [ ] p2-lgbm-test: Phase 2.3: LightGBM compatibility test. Same as 2.2 with LGBMClassifier. 🔴
  _PASS: works like CatBoost. FAIL: may need wrapper adjustments_
- [ ] p2-ensemble-test: Phase 2.4: Ensemble compatibility test. Create sklearn wrapper for ModelEnsemble, test with MapieClassifier. 🔴
  _PASS: wrapper implements fit/predict/predict_proba, MAPIE accepts it. DELIVERABLE: Working sklearn wrapper code_
- [ ] p2-decision: ⚠️ DECISION POINT 1: After Phase 2 - Does MAPIE work with our models? If NO → investigate alternatives. If YES → proceed to Phase 3. 🔴
  _REQUIRES YOUR INPUT before proceeding_
- [ ] p3-sample-size: Phase 3.1: Calibration sample size experiment. Test MAPIE with 20/50/100/200/500 cal samples. Measure: coverage vs target, set size variance, stability. 🔴
  _GOAL: Find minimum samples for stable coverage (<5% variance). Expected: 100+ needed_
- [ ] p3-stability: Phase 3.2: Coverage stability analysis. Run same config 5x with different seeds. Measure coverage variance, set size variance. 🔴
  _PASS: variance <5% at chosen sample size. FAIL: need more samples or different approach_
- [ ] p3-strategy-eval: Phase 3.3: Evaluate calibration strategies. Options: A) Expand L2 cal window, B) Cumulative cal (all past), C) Rolling window (last N), D) Post-hoc. Evaluate each for: train impact, temporal validity, cost, complexity. 🔴
  _DELIVERABLE: Comparison table with pros/cons for each strategy_
- [ ] p3-decision: ⚠️ DECISION POINT 2: After Phase 3 - Which calibration strategy? A/B/C/D? What sample size? 🔴
  _REQUIRES YOUR INPUT. This affects pipeline design significantly._
- [ ] p4-cls-methods: Phase 4.1: Classification methods comparison. Test lac/aps/score on direction_1bar with 100+ cal samples. Measure: coverage@0.1, avg set size, time. 🟡
  _GOAL: Find method with best coverage + smallest sets_
- [ ] p4-multiclass: Phase 4.2: Multiclass test on vol_regime_1bar (3 classes). Measure coverage per class, set size distribution. 🟡
  _GOAL: Verify methods work for 3-class problem_
- [ ] p4-reg-methods: Phase 4.3: Regression methods comparison. Test naive/enbpi on returns_1bar. Measure: coverage@0.1, interval width, stability. 🟡
  _GOAL: Find method with best coverage + tightest intervals. EnbPI expected best for time series._
- [ ] p4-decision: ⚠️ DECISION POINT 3: After Phase 4 - Which method for classification? Which for regression? 🟡
  _REQUIRES YOUR INPUT. Recommendations based on test results._
- [ ] p5-fixed-alpha: Phase 5.1: Baseline with fixed alpha=0.1. Run walk-forward, measure rolling coverage, coverage during regime changes. 🟡
  _GOAL: Establish baseline. If coverage stable at 90% → ACI may not be needed_
- [ ] p5-aci-test: Phase 5.2: ACI test with gamma=0.01. Measure alpha trajectory, coverage stability vs fixed, recovery time after shift. 🟡
  _GOAL: Does ACI improve coverage stability during regime changes?_
- [ ] p5-gamma-sens: Phase 5.3: Gamma sensitivity test. Try 0.001/0.01/0.05/0.1. Measure responsiveness vs stability trade-off. 🟡
  _DELIVERABLE: Recommended gamma with evidence_
- [ ] p5-decision: ⚠️ DECISION POINT 4: After Phase 5 - Enable ACI or use fixed alpha? If ACI, what gamma? 🟡
  _REQUIRES YOUR INPUT. Based on coverage stability results._
- [ ] p6-config-design: Phase 6.1: Design ConformalConfig dataclass. Include: enable, alpha, method_cls, method_reg, min_cal_samples, enable_aci, aci_gamma, cal_strategy. 🟡
  _Use validated values from Phases 3-5_
- [ ] p6-integration-design: Phase 6.2: Design integration points. WHERE: after ModelEnsemble.predict(), before PositionSizer. HOW: wrapper vs direct, optional vs always-on. 🟡
  _DELIVERABLE: Technical design document_
- [ ] p6-output-design: Phase 6.3: Design extended EnsembleOutput. Add: y_pred_set, y_interval, uncertainty, current_alpha. 🟡
  _DELIVERABLE: Updated dataclass definition_
- [ ] p7-module-create: Phase 7.1: Create calibration/ module structure. __init__.py, config.py, classifier.py, regressor.py, aci.py 🟡
  _DELIVERABLE: Empty module structure with docstrings_
- [ ] p7-impl-classifier: Phase 7.2: Implement ConformalClassifier. Wrap MapieClassifier, handle cv=prefit, implement partial_fit if available. 🟡
  _DELIVERABLE: Working ConformalClassifier with tests_
- [ ] p7-impl-regressor: Phase 7.3: Implement ConformalRegressor. Wrap MapieTimeSeriesRegressor, implement EnbPI method. 🟡
  _DELIVERABLE: Working ConformalRegressor with tests_
- [ ] p7-impl-aci: Phase 7.4: Implement AdaptiveConformalInference. Online alpha adaptation, per-target tracking, gamma config. 🟡
  _DELIVERABLE: Working ACI class with tests_
- [ ] p7-ensemble-extend: Phase 7.5: Extend ModelEnsemble. Add conformal_fit(), conformal_predict(), extend EnsembleOutput. 🟡
  _DELIVERABLE: Updated ensemble.py with conformal support_
- [ ] p8-pipeline-mod: Phase 8.1: Modify pipeline.py. Add conformal calibration step, add ACI update step, pass enhanced outputs forward. 🟡
  _DELIVERABLE: Updated pipeline.py with conformal integration_
- [ ] p8-position-sizer: Phase 8.2: Modify PositionSizer (if applicable). Use uncertainty for position scaling, use intervals for risk management. 🟢
  _OPTIONAL: Only if position sizer uses probabilities_
- [ ] p9-full-test: Phase 9.1: Run all 20 configs with conformal. Measure: coverage (90%±3%), set size/interval width, time overhead. 🔴
  _PASS: coverage 87-93% for all configs. FAIL: investigate problematic configs_
- [ ] p9-shift-test: Phase 9.2: Distribution shift test. Use 2022 bear market, 2023 recovery periods. Compare ACI vs fixed coverage stability. 🟡
  _GOAL: ACI should maintain better coverage during shifts_
- [ ] p9-comparison: Phase 9.3: Performance comparison vs baseline. Does uncertainty help position sizing? Any metric degradation? 🟡
  _DELIVERABLE: Before/after comparison report_
- [ ] p9-decision: ⚠️ DECISION POINT 5: After Phase 9 - Is overhead worth the benefit? Keep or revert? 🔴
  _REQUIRES YOUR INPUT. Final go/no-go decision._
- [ ] p10-arch-doc: Phase 10.1: Update ARCHITECTURE.md. Add Layer 3 documentation, configuration options. 🟢
  _DELIVERABLE: Updated architecture documentation_
- [ ] p10-session-doc: Phase 10.2: Update session.md. Record validation results, decisions made, lessons learned. 🟢
  _DELIVERABLE: Complete session record_
- [ ] p10-examples: Phase 10.3: Create usage examples. How to enable/disable conformal, interpret outputs. 🟢
  _DELIVERABLE: Example code in docstrings or separate file_