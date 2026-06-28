# RPF Regime Suppression Simulator

## Purpose

Offline replay of regime/change-risk suppression rules. This does not change router decisions.

- regime diagnostic run: `test_output/rpf_ranked_signal_regime_diagnostic/20260628_150140_rank_signal_regime_diagnostic`

## Summary

| Scope | Side | Candidate | Windows | Suppressed | Signals Before | Signals After | Precision Before | Precision After | Lift Before | Lift After | FDR Before | FDR After | FP Reduction |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| overall | down | down_rocket_16_diag_v1 | 1920 | 1126 | 3015 | 1279 | 0.392703 | 0.413604 | 1.02408 | 1.07858 | 0.607297 | 0.586396 | 0.590388 |
| overall | up | up_rocket_64_v1 | 1920 | 668 | 2678 | 1762 | 0.415609 | 0.429625 | 1.07169 | 1.10784 | 0.584391 | 0.570375 | 0.357827 |
| source_run | down | down_rocket_16_diag_v1 | 960 | 606 | 1476 | 569 | 0.405827 | 0.414763 | 1.04197 | 1.06492 | 0.594173 | 0.585237 | 0.620296 |
| source_run | down | down_rocket_16_diag_v1 | 960 | 520 | 1539 | 710 | 0.380117 | 0.412676 | 1.00704 | 1.09329 | 0.619883 | 0.587324 | 0.562893 |
| source_run | up | up_rocket_64_v1 | 960 | 340 | 1305 | 862 | 0.407663 | 0.424594 | 1.08642 | 1.13154 | 0.592337 | 0.575406 | 0.358344 |
| source_run | up | up_rocket_64_v1 | 960 | 328 | 1373 | 900 | 0.423161 | 0.434444 | 1.0569 | 1.08509 | 0.576839 | 0.565556 | 0.357323 |

## Interpretation

- Useful suppression should raise precision/lift and reduce FDR without collapsing signals.
- If signal retention is too low, this is a risk filter only, not a complete trading workflow.
