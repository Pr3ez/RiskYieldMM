# HTF Phase 9 Preflight Resolution

Date: 2026-03-18

## Scope
- Resolve the Phase 9 preflight ambiguity around shifted `C` feature trees.
- Verify whether the issue is in the production pipeline or only in the
  read-only preflight model.

## Evidence Reviewed
- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)
- [htf_phase9_preflight.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_phase9_preflight.py)
- [htf_phase9_feature_propagation_check.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_phase9_feature_propagation_check.json)

## Findings
- The production pipeline is not the problem.
- Shifted `C` feature batches are built from base `B` feature batches in
  `_build_shifted_feature_batches_from_base(...)`.
- In a real Phase 9 run, once `B` feature trees are rebuilt onto the richer
  `151`-column schema, the shifted `C` feature stage will see:
  - a changed `base_features` fingerprint
  - a changed source-derived schema
- That means shifted `C` feature trees should be treated as `full_recompute`,
  not `current`.
- The ambiguity came from the read-only Phase 9 preflight model, which was
  comparing `C` against the current on-disk `B` schema instead of propagating
  the expected upstream `B` refresh.

## Resolution
- Updated [htf_phase9_preflight.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_phase9_preflight.py)
  so the expected-run model promotes shifted `C` feature stages when the base
  `B` feature stage is expected to refresh.
- Validation artifact confirms the corrected expectation:
  - all shifted `C` feature trees for `8h`, `24h`, and `7d`
  - for both `1m` and `15m`
  - should be `full_recompute`
  - with expected schema count `151`

## Implication For Phase 9
- Combined trees stay current.
- Label trees stay current.
- Both `B` and `C` feature trees for `1m` and `15m` must refresh.
- Downstream `1m / target_4class` optimized trees, helper-cache trees, and
  helper output trees should also be treated as dirty after the feature refresh.

## Artifact Safety
- This was a read-only verification step.
- No production HTF artifacts were intentionally rebuilt, cleared, removed, or
  overwritten while resolving this ambiguity.

## Conclusion
- The ambiguity is resolved.
- Phase 9 guidance is now accurate enough to use for the actual controlled
  richer-feature schema promotion.
