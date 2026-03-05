# Production Setup Analysis (1m/target_4class, 24 configs)

Date: 2026-02-27

## Current state
- Latest full pipeline run: `20260227_141406_prod_full3500_cfg24`.
- Leakage guard: PASS (`violations=0` for per-config and router checks).
- Status: `not_production_ready`.

## Key diagnostics
- Training operating point selected (`threshold=0.60`) is already near-feasible only:
  - directional_active_safe_accuracy = 0.4774
  - opposite_fp_rate_active = 0.5188
  - opposite_fp_rate_covered = 0.0460
  - cadence = 11.27 batches/signal
- Holdout degradation is severe:
  - directional_active_safe_accuracy = 0.3684
  - opposite_fp_rate_active = 0.6316
  - opposite_fp_rate_covered = 0.0240
  - active_batches = 19 / 500 (cadence 26.3)

## Selector quality checks (holdout)
- Best fixed single config directional accuracy: ~0.51.
- Router top-1 (no threshold) directional accuracy: ~0.488.
- Router-selected config mean batch dir-accuracy: ~0.505.
- Mean over all configs per batch: ~0.515.
- Oracle upper bound (pick best config with lookahead): ~0.874.

Interpretation:
- There is substantial per-batch opportunity (oracle gap), but the current router target/features are not ranking configs correctly in real time.

## Production-safe setup changes (next)
1. Replace binary `hit>=0.70` routing target with direct ranking objective on `actual_dir_acc` (per-batch, 24-way ranking).
2. Add pairwise diversity/consensus features (distance-to-peer predictions, rank in confidence margin).
3. Add short-horizon drift features (recent 25/50/100 batch performance deltas per config).
4. Keep strict causal walk-forward and final untouched holdout (last 500).
5. Select operating threshold by risk-first constraints only.

## Promotion gate (unchanged)
- directional_active_safe_accuracy >= 0.70
- opposite_fp_rate_active <= 0.25
- opposite_fp_rate_covered <= 0.03
- cadence within 10-15 batches/signal

If no feasible point exists, mark as not production ready and output nearest-feasible candidate with explicit violations.
