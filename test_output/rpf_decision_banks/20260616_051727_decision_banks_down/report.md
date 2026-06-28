# RPF Separate Decision Bank Plan

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `down`
- `windows`: `50`
- `classifier_score_path`: `test_output/rpf_clean_classification/20260615_181239_classification_cls_extreme_down_ge_2x_up_hvol_v2/prediction_scores.parquet`

## Config

- `target_positive_batch_min_rate`: `0.8`
- `target_opposite_batch_max_rate`: `0.2`
- `target_train_positive_batches`: `80`
- `target_train_negative_batches`: `160`
- `target_val_positive_batches`: `20`
- `target_val_negative_batches`: `40`
- `gate_min_active_rows`: `10`
- `gate_trust_min_precision`: `0.7`
- `gate_reject_min_fp_rate`: `0.7`
- `gate_train_trust_batches`: `80`
- `gate_train_reject_batches`: `160`
- `gate_val_trust_batches`: `20`
- `gate_val_reject_batches`: `40`
- `candidate_lookback_batches`: `2000`
- `label_maturity_embargo_batches`: `1`

## Summary

- `windows`: `50`
- `target_bank_usable_window_rate`: `1`
- `gate_bank_usable_window_rate`: `0`
- `target_train_batch_count_min`: `240`
- `target_val_batch_count_min`: `60`
- `gate_train_batch_count_min`: `0`
- `gate_val_batch_count_min`: `0`
- `gate_train_precision_weighted_mean`: `-`
- `gate_train_fp_rate_weighted_mean`: `-`
- `any_maturity_violations`: `False`

## Interpretation

Target-bank batches train the main UP/DOWN event model. Gate-bank batches train the trust filter from historical classifier true-positive and false-positive behavior. Both banks are mature before the prediction batch.
