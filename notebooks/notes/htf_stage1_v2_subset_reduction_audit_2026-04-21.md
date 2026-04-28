# HTF Stage-1-v2 Subset Reduction Audit

Date: 2026-04-21
Scope: full fixed-policy `8h/B` window
Run: `stage1_catboost_8h_b_v2_fixed_policy_pb5170_5669_live`

## Goal

Check whether reducing the candidate combo pool can preserve most of the held-out
winner directional ceiling while simplifying the problem.

This audit uses an exhaustive subset search over all `2^8 - 1 = 255` non-empty combo
subsets.

Important: this is an **oracle-within-subset** audit, not a live selector audit.

For each fixed subset:

1. On each step, take the best available combo inside that subset using the realized
   `filtered_rank`.
2. Split chronologically into train/test (`350 / 150` steps).
3. Choose the subset by **train** winner directional accuracy.
4. Measure how much held-out winner quality is lost relative to the full 8-combo pool.

Implementation:

- [htf_stage1_v2_subset_reduction_audit.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_v2_subset_reduction_audit.py)

Artifacts:

- [summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_subset_reduction_audit_20260421_8h_b_pb5170_5669/summary.json)
- [best_subset_per_size.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_subset_reduction_audit_20260421_8h_b_pb5170_5669/best_subset_per_size.csv)
- [all_subset_metrics.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_subset_reduction_audit_20260421_8h_b_pb5170_5669/all_subset_metrics.csv)

## Full-Pool Baseline

Held-out test upper bound with all 8 combos:

- winner directional accuracy: `0.712194`
- winner class accuracy: `0.526611`
- global top-1 capture rate: `1.00`

This is the ceiling any reduced subset is trying to approximate.

## Best Subset By Size

| size | best subset by train dir acc | test dir acc | dir gap vs full | test acc | acc gap vs full | top-1 capture |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | `f2_v2_t4` | `0.530222` | `-0.181972` | `0.277167` | `-0.249444` | `0.10` |
| 2 | `f2_v1_t3,f2_v2_t10` | `0.589528` | `-0.122667` | `0.360639` | `-0.165972` | `0.2133` |
| 3 | `f2_v1_t3,f2_v2_t10,f2_v2_t4` | `0.645333` | `-0.066861` | `0.412611` | `-0.114000` | `0.3133` |
| 4 | `f2_v1_t3,f2_v1_t6,f2_v2_t10,f2_v2_t4` | `0.662278` | `-0.049917` | `0.440944` | `-0.085667` | `0.4333` |
| 5 | `f2_v1_t3,f2_v1_t6,f2_v2_t10,f2_v2_t4,f7_v1_t4` | `0.677944` | `-0.034250` | `0.464750` | `-0.061861` | `0.54` |
| 6 | `f2_v1_t3,f2_v1_t5,f2_v1_t6,f2_v2_t10,f2_v2_t4,f7_v1_t4` | `0.692333` | `-0.019861` | `0.485083` | `-0.041528` | `0.72` |
| 7 | `f2_v1_t3,f2_v1_t5,f2_v1_t6,f2_v2_t10,f2_v2_t4,f2_v3_t9,f7_v1_t4` | `0.712139` | `-0.000056` | `0.511111` | `-0.015500` | `0.88` |
| 8 | full pool | `0.712194` | `0.000000` | `0.526611` | `0.000000` | `1.00` |

## Main Finding

Yes, you can reduce candidates and keep almost all of the held-out **directional**
oracle ceiling, but only if you reduce very little.

The strongest result is the best size-7 subset:

- keep:
  - `f2_v1_t3`
  - `f2_v1_t5`
  - `f2_v1_t6`
  - `f2_v2_t10`
  - `f2_v2_t4`
  - `f2_v3_t9`
  - `f7_v1_t4`
- drop:
  - `f2_v2_t8`

That subset gives:

- held-out directional accuracy `0.712139`
- full-pool directional accuracy `0.712194`
- gap only `-0.000056`

So in pure directional ceiling terms, dropping `f2_v2_t8` barely changes the result.

## But The Tradeoff Is Real

That same size-7 subset still loses:

- class accuracy: `0.511111` vs full `0.526611`
- top-1 capture rate: `0.88` vs full `1.00`

Interpretation:

- it nearly preserves directional ceiling
- but it still misses the full-pool best combo on `12%` of held-out steps
- and the steps it misses are costly enough to reduce class accuracy by `0.0155`

So the simplification is not free.

## What This Means

### If the target is directional ceiling only

Then a very light prune may be acceptable:

- dropping only `f2_v2_t8` changes almost nothing in held-out directional ceiling

### If the target is the overall best available winner quality

Then the full 8-combo pool is still better.

That is especially clear in:

- class accuracy
- top-1 capture rate
- general opportunity set per step

### If the target is easier live selection

This audit alone is not enough.

Because this uses the **oracle best within subset**, it only answers:

- “How much ceiling do we lose if we remove combos?”

It does **not** answer:

- “Will a real live selector become more accurate with fewer candidates?”

That would require a separate train/test selector audit using an actual selection rule.

## Bottom Line

Reducing candidates can help only in a limited sense.

- Aggressive pruning is clearly harmful.
- Moderate pruning still costs real winner quality.
- The only prune that looks nearly harmless on directional ceiling is dropping just one
  combo (`f2_v2_t8`) from the current 8-combo pool.

So the practical answer is:

- **do not** cut the pool aggressively
- if you want to test simplification, the only defensible first experiment is a
  7-combo pool with `f2_v2_t8` removed
- even then, you should expect lower class accuracy and lower winner coverage

