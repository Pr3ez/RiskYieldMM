# Winner Dependency Addendum (Last 500 Common Batches)

- Generated (UTC): 2026-02-21T10:10:29.564231+00:00
- Based on: `step_winner_diagnostics_last500.csv`
- High bucket: winner_accuracy > 0.60

## Global High vs Low
- HIGH: steps=1379, acc=0.788, dir_acc=0.863, cross_dir_err=0.085, up_recall=0.732, down_recall=0.775, fold_mean=1.53
- LOW: steps=1268, acc=0.409, dir_acc=0.573, cross_dir_err=0.344, up_recall=0.551, down_recall=0.581, fold_mean=1.95

## Direction Asymmetry (UP vs DOWN)
- `target_4class`: down recall is consistently higher than up recall in both HIGH and LOW buckets.
- `target_breakfree`: HIGH bucket is near-balanced (up/down recall close); LOW bucket tends to degrade into UP bias and larger cross-direction error.

Most UP-biased LOW buckets (pred_up - true_up):
- 15m/target_breakfree: bias=0.102, dir_acc=0.498, cross_err=0.322
- 5m/target_breakfree: bias=0.098, dir_acc=0.502, cross_err=0.299
- 1m/target_breakfree: bias=0.046, dir_acc=0.502, cross_err=0.289
- 5m/target_4class: bias=-0.046, dir_acc=0.631, cross_err=0.369

## Source Snapshot Comparison
- Compared winner rows coming from `current` vs `archive:*` snapshots.
- 15m/target_4class: archive: n=52, high_rate=0.538, dir_acc=0.756; current: n=382, high_rate=0.348, dir_acc=0.712
- 15m/target_breakfree: archive: n=56, high_rate=0.625, dir_acc=0.689; current: n=409, high_rate=0.631, dir_acc=0.725
- 1m/target_4class: archive: n=196, high_rate=0.408, dir_acc=0.733; current: n=155, high_rate=0.523, dir_acc=0.771
- 1m/target_breakfree: archive: n=86, high_rate=0.593, dir_acc=0.681; current: n=380, high_rate=0.595, dir_acc=0.717
- 5m/target_4class: archive: n=67, high_rate=0.418, dir_acc=0.724; current: n=393, high_rate=0.425, dir_acc=0.737
- 5m/target_breakfree: archive: n=53, high_rate=0.604, dir_acc=0.712; current: n=418, high_rate=0.622, dir_acc=0.721

## Missing Diagnostics (coverage gap)
- Missing rows are only `winner_rows_missing` from source snapshots.
- 1m/target_4class: 149 missing steps
- 15m/target_4class: 66 missing steps
- 5m/target_4class: 40 missing steps
- 15m/target_breakfree: 35 missing steps
- 1m/target_breakfree: 34 missing steps
- 5m/target_breakfree: 29 missing steps

## Practical Interpretation
- Strong winner periods are associated with lower fold-count recipes and materially lower opposite-direction errors.
- Weak periods are associated with recipe sets that over-predict UP in breakfree units and under-represent HOLD.
- 1m/target_4class has the largest coverage gap, so treat unit-level conclusions there as lower-confidence until gap is closed.
