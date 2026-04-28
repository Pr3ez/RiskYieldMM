# HTF Walk-Forward Diagnostics Merge - 2026-04-11

## Scope

Merge the split HTF walk-forward diagnostics outputs from multiple long-running runs into one consolidated output root.

## Source Roots Used

- `test_output/htf_walkforward_diagnostics/20260402_181239`
  - audit-only canonical base
- `test_output/htf_walkforward_diagnostics/20260402_183558`
  - winner-only `PredictionValuesChange`
  - winner-only `LossFunctionChange`
  - root-topk `PredictionValuesChange` for all roots except `7d/C`
- `test_output/htf_walkforward_diagnostics/20260407_030231`
  - root-topk `PredictionValuesChange` for `7d/C`
- `test_output/htf_walkforward_diagnostics/20260407_065956`
  - root-topk `LossFunctionChange` for `8h/B`, `8h/C`
- `test_output/htf_walkforward_diagnostics/20260408_132339`
  - root-topk `LossFunctionChange` for `24h/B`, `24h/C`
- `test_output/htf_walkforward_diagnostics/20260409_213110`
  - root-topk `LossFunctionChange` for `7d/B`, `7d/C`

## Merge Output

Consolidated merged root:

- `test_output/htf_walkforward_diagnostics/20260411_153744_merged`

Merge utility:

- `scripts/analysis/merge_htf_walkforward_diagnostics_runs.py`

## Validation Result

The merged root is complete.

Validated:

- expected Step-2 blocks present: `24 / 24`
- missing blocks: `0`
- phases present:
  - `winner_only`
  - `root_topk`
- feature-importance types present:
  - `PredictionValuesChange`
  - `LossFunctionChange`

Aggregate outputs regenerated successfully:

- `step2_aggregate_artifacts.parquet`: `108` rows
- `winner_vs_near_winner_overlap.parquet`: `24` rows
- `recommendations.parquet`: `17` rows

Per-scope artifact indexes regenerated:

- `step2_winner_only_PredictionValuesChange_artifacts.csv`
- `step2_winner_only_LossFunctionChange_artifacts.csv`
- `step2_root_topk_PredictionValuesChange_artifacts.csv`
- `step2_root_topk_LossFunctionChange_artifacts.csv`

## Resulting Structure

The merged root now contains:

- canonical audit outputs
- full `winner_only` Step-2 outputs for all six roots
- full `root_topk` Step-2 outputs for all six roots
- merged feature-quality views
- merged winner-vs-near-winner overlap tables
- regenerated recommendations
- merge manifest and merged run summary

## Conclusion

The split diagnostics runs were successfully consolidated into one complete root without rerunning the heavy computations.

This merged root should be treated as the canonical combined output for the current full HTF walk-forward diagnostics sweep.
