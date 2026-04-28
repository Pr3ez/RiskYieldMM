# Production Config-Selection Evaluation (Full 500)

- Generated (UTC): 2026-02-21T13:23:18.719939+00:00
- Evaluation model: same_period_close + history_brier_ewma + strict_agreement_margin
- Fairness rule: compare variants against baseline on common anchors only.

## Full-run metrics (headline)
- baseline: rows=6688, macro_f1=0.5053, opp_fp_cov=0.0843, cost=0.1687
- fullsupport_diverse_risk: rows=6688, macro_f1=0.5194, opp_fp_cov=0.0984, cost=0.1968
- fullsupport_risk: rows=6688, macro_f1=0.5504, opp_fp_cov=0.0707, cost=0.1414
- fullsupport_stability: rows=6688, macro_f1=0.5471, opp_fp_cov=0.1093, cost=0.2186

## Common-anchor comparison vs baseline
- baseline: common_rows=6688, dir_acc=0.5053, opp_fp_cov=0.0843, cost=0.1687
- fullsupport_diverse_risk: common_rows=6688, dir_acc=0.5194, opp_fp_cov=0.0984, cost=0.1968
- fullsupport_risk: common_rows=6688, dir_acc=0.5504, opp_fp_cov=0.0707, cost=0.1414
- fullsupport_stability: common_rows=6688, dir_acc=0.5471, opp_fp_cov=0.1093, cost=0.2186

## Ranking + Gates
- rank 1 fullsupport_risk: all_pass=True, rows95=True, dir>=base=True, opp<=base=True, cost<=base=True
- rank 2 baseline: all_pass=True, rows95=True, dir>=base=True, opp<=base=True, cost<=base=True
- rank 3 fullsupport_diverse_risk: all_pass=False, rows95=True, dir>=base=True, opp<=base=False, cost<=base=False
- rank 4 fullsupport_stability: all_pass=False, rows95=True, dir>=base=True, opp<=base=False, cost<=base=False

## Recommendation
- fullsupport_risk
- Note: still require one additional confirmation run with the same candidate set and frozen seed.