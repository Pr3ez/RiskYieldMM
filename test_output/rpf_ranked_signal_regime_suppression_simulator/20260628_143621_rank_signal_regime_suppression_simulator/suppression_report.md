# RPF Regime Suppression Simulator

## Purpose

Offline replay of regime/change-risk suppression rules. This does not change router decisions.

- regime diagnostic run: `test_output/rpf_ranked_signal_regime_diagnostic/20260628_142856_rank_signal_regime_diagnostic`

## Summary

| Scope | Side | Candidate | Windows | Suppressed | Signals Before | Signals After | Precision Before | Precision After | Lift Before | Lift After | FDR Before | FDR After | FP Reduction |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| overall | down | down_rocket_16_diag_v1 | 1920 | 663 | 3015 | 1977 | 0.392703 | 0.408194 | 1.02408 | 1.06447 | 0.607297 | 0.591806 | 0.361005 |
| overall | up | up_rocket_64_v1 | 1920 | 660 | 2678 | 1777 | 0.415609 | 0.426562 | 1.07169 | 1.09994 | 0.584391 | 0.573438 | 0.348882 |
| source_run | down | down_rocket_16_diag_v1 | 960 | 368 | 1476 | 899 | 0.405827 | 0.414905 | 1.04197 | 1.06528 | 0.594173 | 0.585095 | 0.400228 |
| source_run | down | down_rocket_16_diag_v1 | 960 | 295 | 1539 | 1078 | 0.380117 | 0.402597 | 1.00704 | 1.06659 | 0.619883 | 0.597403 | 0.324948 |
| source_run | up | up_rocket_64_v1 | 960 | 324 | 1305 | 883 | 0.407663 | 0.409966 | 1.08642 | 1.09256 | 0.592337 | 0.590034 | 0.326003 |
| source_run | up | up_rocket_64_v1 | 960 | 336 | 1373 | 894 | 0.423161 | 0.442953 | 1.0569 | 1.10634 | 0.576839 | 0.557047 | 0.371212 |

## Interpretation

- Useful suppression should raise precision/lift and reduce FDR without collapsing signals.
- If signal retention is too low, this is a risk filter only, not a complete trading workflow.
