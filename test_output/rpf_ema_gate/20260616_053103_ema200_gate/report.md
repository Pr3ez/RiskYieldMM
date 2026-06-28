# RPF EMA200 Gate Evaluation

## Scope

- `asset`: `BTCUSDT`
- `timeframes`: `15m,1h,4h,1d`
- `buffers`: `0.0,0.001,0.0025,0.005`
- `up_score_path`: `test_output/rpf_clean_classification/20260615_164900_classification_cls_extreme_up_ge_2x_down_hvol_v2/prediction_scores.parquet`
- `down_score_path`: `test_output/rpf_clean_classification/20260615_181239_classification_cls_extreme_down_ge_2x_up_hvol_v2/prediction_scores.parquet`

## Contract

UP uses current 1m close above the last closed timeframe EMA200. DOWN uses current 1m close below the last closed timeframe EMA200. EMA bars are joined by closed-bar timestamp only.

## Outputs

- `summary`: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/test_output/rpf_ema_gate/20260616_053103_ema200_gate/ema_gate_summary.parquet`
- `row_scores`: `['/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/test_output/rpf_ema_gate/20260616_053103_ema200_gate/ema_gate_scores_15m.parquet', '/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/test_output/rpf_ema_gate/20260616_053103_ema200_gate/ema_gate_scores_1h.parquet', '/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/test_output/rpf_ema_gate/20260616_053103_ema200_gate/ema_gate_scores_4h.parquet', '/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/test_output/rpf_ema_gate/20260616_053103_ema200_gate/ema_gate_scores_1d.parquet']`
