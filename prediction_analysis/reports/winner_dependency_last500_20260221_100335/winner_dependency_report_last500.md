# Winner Dependency Report (Last 500 Common Batches)

- Generated (UTC): 2026-02-21T10:03:35.773954+00:00
- Batches analyzed: 500 (min=5072, max=5571)
- Units analyzed: 6
- Threshold: high accuracy if winner_accuracy > 0.60

## 1m/target_4class
- steps: 263, high(>0.60): 114, low: 149, high_rate: 0.433
- HIGH: acc=0.765, dir_acc=0.888, cross_dir_err=0.112, true_up=0.492, pred_up=0.461, fold_mean=2.04
- LOW: acc=0.411, dir_acc=0.638, cross_dir_err=0.362, true_up=0.520, pred_up=0.469, fold_mean=2.09
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f2_v1_t3: wins=22, high=22 (1.000), uplift=0.567, dir_acc=0.949, pred_up=0.565
  - f2_v2_t8: wins=10, high=10 (1.000), uplift=0.567, dir_acc=0.878, pred_up=0.575
  - f2_v3_t9: wins=8, high=8 (1.000), uplift=0.567, dir_acc=0.889, pred_up=0.344
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f2_v1_t5: wins=40, high=11 (0.275), uplift=-0.158, dir_acc=0.714, pred_up=0.307
  - f3_v2_t4: wins=18, high=5 (0.278), uplift=-0.156, dir_acc=0.655, pred_up=0.619
  - f2_v1_t4: wins=38, high=11 (0.289), uplift=-0.144, dir_acc=0.717, pred_up=0.469

## 1m/target_breakfree
- steps: 402, high(>0.60): 235, low: 167, high_rate: 0.585
- HIGH: acc=0.802, dir_acc=nan, cross_dir_err=nan, true_up=0.407, pred_up=0.414, fold_mean=1.30
- LOW: acc=0.437, dir_acc=nan, cross_dir_err=nan, true_up=0.351, pred_up=0.404, fold_mean=2.02
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f1_v3_t21: wins=27, high=21 (0.778), uplift=0.193, dir_acc=0.803, pred_up=0.374
  - f1_v3_t27: wins=21, high=15 (0.714), uplift=0.130, dir_acc=0.665, pred_up=0.332
  - f1_v2_t18: wins=30, high=21 (0.700), uplift=0.115, dir_acc=0.750, pred_up=0.426
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f2_v3_t27: wins=14, high=4 (0.286), uplift=-0.299, dir_acc=0.638, pred_up=0.495
  - f2_v2_t16: wins=5, high=2 (0.400), uplift=-0.185, dir_acc=0.654, pred_up=0.412
  - f2_v4_t32: wins=8, high=4 (0.500), uplift=-0.085, dir_acc=0.578, pred_up=0.366

## 5m/target_4class
- steps: 415, high(>0.60): 175, low: 240, high_rate: 0.422
- HIGH: acc=0.749, dir_acc=0.869, cross_dir_err=0.131, true_up=0.461, pred_up=0.464, fold_mean=1.54
- LOW: acc=0.394, dir_acc=0.638, cross_dir_err=0.362, true_up=0.512, pred_up=0.466, fold_mean=2.01
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f2_v2_t8: wins=5, high=4 (0.800), uplift=0.378, dir_acc=0.842, pred_up=0.487
  - f1_v2_t6: wins=17, high=12 (0.706), uplift=0.284, dir_acc=0.875, pred_up=0.485
  - f1_v1_t5: wins=18, high=11 (0.611), uplift=0.189, dir_acc=0.720, pred_up=0.538
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f2_v2_t10: wins=7, high=1 (0.143), uplift=-0.279, dir_acc=0.676, pred_up=0.524
  - f2_v1_t4: wins=6, high=1 (0.167), uplift=-0.255, dir_acc=0.788, pred_up=0.503
  - f3_v2_t10: wins=5, high=1 (0.200), uplift=-0.222, dir_acc=0.613, pred_up=0.321

## 5m/target_breakfree
- steps: 434, high(>0.60): 265, low: 169, high_rate: 0.611
- HIGH: acc=0.796, dir_acc=0.846, cross_dir_err=0.071, true_up=0.404, pred_up=0.431, fold_mean=1.38
- LOW: acc=0.422, dir_acc=nan, cross_dir_err=nan, true_up=0.321, pred_up=0.428, fold_mean=1.62
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f3_v3_t24: wins=5, high=4 (0.800), uplift=0.189, dir_acc=0.804, pred_up=0.562
  - f1_v4_t28: wins=30, high=23 (0.767), uplift=0.156, dir_acc=0.773, pred_up=0.465
  - f1_v2_t18: wins=28, high=21 (0.750), uplift=0.139, dir_acc=0.740, pred_up=0.379
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f2_v3_t21: wins=6, high=2 (0.333), uplift=-0.277, dir_acc=0.583, pred_up=0.375
  - f2_v4_t12: wins=8, high=3 (0.375), uplift=-0.236, dir_acc=0.566, pred_up=0.401
  - f1_v4_t32: wins=34, high=16 (0.471), uplift=-0.140, dir_acc=0.660, pred_up=0.398

## 15m/target_4class
- steps: 399, high(>0.60): 140, low: 259, high_rate: 0.351
- HIGH: acc=0.770, dir_acc=0.888, cross_dir_err=0.112, true_up=0.422, pred_up=0.413, fold_mean=1.58
- LOW: acc=0.392, dir_acc=0.618, cross_dir_err=0.382, true_up=0.517, pred_up=0.456, fold_mean=2.02
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f5_v2_t8: wins=7, high=5 (0.714), uplift=0.363, dir_acc=0.812, pred_up=0.286
  - f2_v1_t5: wins=6, high=3 (0.500), uplift=0.149, dir_acc=0.812, pred_up=0.365
  - f1_v2_t4: wins=32, high=15 (0.469), uplift=0.118, dir_acc=0.738, pred_up=0.400
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f4_v1_t5: wins=5, high=1 (0.200), uplift=-0.151, dir_acc=0.700, pred_up=0.525
  - f3_v1_t4: wins=9, high=2 (0.222), uplift=-0.129, dir_acc=0.660, pred_up=0.312
  - f2_v1_t4: wins=13, high=3 (0.231), uplift=-0.120, dir_acc=0.678, pred_up=0.543

## 15m/target_breakfree
- steps: 419, high(>0.60): 265, low: 154, high_rate: 0.632
- HIGH: acc=0.805, dir_acc=0.847, cross_dir_err=0.072, true_up=0.421, pred_up=0.447, fold_mean=1.30
- LOW: acc=0.431, dir_acc=nan, cross_dir_err=nan, true_up=0.324, pred_up=0.403, fold_mean=1.84
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f2_v3_t15: wins=7, high=6 (0.857), uplift=0.225, dir_acc=0.729, pred_up=0.625
  - f1_v4_t28: wins=25, high=21 (0.840), uplift=0.208, dir_acc=0.829, pred_up=0.480
  - f2_v4_t16: wins=11, high=9 (0.818), uplift=0.186, dir_acc=0.685, pred_up=0.403
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f2_v2_t16: wins=5, high=2 (0.400), uplift=-0.232, dir_acc=0.687, pred_up=0.512
  - f1_v3_t15: wins=27, high=15 (0.556), uplift=-0.077, dir_acc=nan, pred_up=0.481
  - f1_v3_t21: wins=32, high=18 (0.562), uplift=-0.070, dir_acc=0.682, pred_up=0.320

## Cross-Unit Aggregate
- Global HIGH count=1194, LOW count=1138, HIGH rate=0.512
- Mean directional_accuracy: HIGH=nan, LOW=nan
- Mean directional_cross_error: HIGH=nan, LOW=nan
- Mean fold_count: HIGH=1.45, LOW=1.94