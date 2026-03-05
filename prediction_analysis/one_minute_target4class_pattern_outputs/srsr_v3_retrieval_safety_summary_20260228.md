# SRSR v3 Retrieval/Ranker Safety Rerun

## Runs
| run | safe_acc | coverage | opp_active | opp_covered | active_batches | batches_per_signal |
|---|---:|---:|---:|---:|---:|---:|
| 20260228_015635_srsr_v3_retrieval_safeA | 0.5625 | 0.0320 | 0.4375 | 0.0140 | 16 | 31.25 |
| 20260228_020116_srsr_v3_retrieval_safeB | 0.5217 | 0.0460 | 0.4783 | 0.0220 | 23 | 21.74 |

## Best run
- `20260228_015635_srsr_v3_retrieval_safeA`

## Delta vs baselines
| baseline | Δsafe_acc | Δcoverage | Δopp_active | Δopp_covered | Δactive_batches |
|---|---:|---:|---:|---:|---:|
| 20260228_014057_srsr_v2_safeA | +0.0625 | +0.0120 | -0.0625 | +0.0040 | +6 |
| 20260228_011726_prod_full3500_cfg24_srsr_v1 | +0.1109 | -0.0300 | -0.1109 | -0.0200 | -15 |
| 20260228_004427_prod_full3500_cfg24_step1_groupwise_ltr_v2 | -0.0153 | -0.0580 | +0.0153 | -0.0240 | -29 |
| 20260227_215602_prod_full3500_cfg24_shift_reject_rollingq_covcon_v1 | -0.1412 | -0.0220 | +0.1412 | -0.0020 | -11 |
