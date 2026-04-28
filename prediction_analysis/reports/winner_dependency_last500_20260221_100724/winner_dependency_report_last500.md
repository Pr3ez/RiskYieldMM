# Winner Dependency Report (Last 500 Common Batches)

- Generated (UTC): 2026-02-21T10:07:24.944085+00:00
- Batches analyzed: 500 (min=5072, max=5571)
- Units analyzed: 6
- Threshold: high accuracy if winner_accuracy > 0.60

## Coverage
- 15m/target_4class: covered=434/500 (0.868)
- 15m/target_breakfree: covered=465/500 (0.930)
- 1m/target_4class: covered=351/500 (0.702)
- 1m/target_breakfree: covered=466/500 (0.932)
- 5m/target_4class: covered=460/500 (0.920)
- 5m/target_breakfree: covered=471/500 (0.942)
- Missing diagnostics rows: 353 (see diagnostic_missing_steps_last500.csv)

## 1m/target_4class
- steps: 351, high(>0.60): 161, low: 190, high_rate: 0.459
- HIGH: acc=0.769, dir_acc=0.888, cross_dir_err=0.112, true_up=0.492, pred_up=0.473, fold_mean=2.03
- LOW: acc=0.405, dir_acc=0.633, cross_dir_err=0.367, true_up=0.534, pred_up=0.476, fold_mean=2.07
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f2_v1_t3: wins=22, high=22 (1.000), uplift=0.541, dir_acc=0.949, pred_up=0.565
  - f2_v2_t8: wins=10, high=10 (1.000), uplift=0.541, dir_acc=0.878, pred_up=0.575
  - f2_v3_t9: wins=8, high=8 (1.000), uplift=0.541, dir_acc=0.889, pred_up=0.344
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f3_v2_t4: wins=18, high=5 (0.278), uplift=-0.181, dir_acc=0.655, pred_up=0.619
  - f2_v1_t5: wins=42, high=13 (0.310), uplift=-0.149, dir_acc=0.725, pred_up=0.293
  - f2_v2_t10: wins=53, high=20 (0.377), uplift=-0.081, dir_acc=0.714, pred_up=0.543

## 1m/target_breakfree
- steps: 466, high(>0.60): 277, low: 189, high_rate: 0.594
- HIGH: acc=0.802, dir_acc=0.852, cross_dir_err=0.062, true_up=0.412, pred_up=0.418, fold_mean=1.40
- LOW: acc=0.435, dir_acc=0.502, cross_dir_err=0.289, true_up=0.352, pred_up=0.398, fold_mean=2.02
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f2_v4_t28: wins=5, high=5 (1.000), uplift=0.406, dir_acc=0.715, pred_up=0.407
  - f1_v3_t21: wins=27, high=21 (0.778), uplift=0.183, dir_acc=0.803, pred_up=0.374
  - f1_v3_t27: wins=21, high=15 (0.714), uplift=0.120, dir_acc=0.665, pred_up=0.332
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f2_v3_t27: wins=15, high=5 (0.333), uplift=-0.261, dir_acc=0.601, pred_up=0.462
  - f2_v4_t32: wins=20, high=10 (0.500), uplift=-0.094, dir_acc=0.636, pred_up=0.496
  - f2_v4_t12: wins=6, high=3 (0.500), uplift=-0.094, dir_acc=0.590, pred_up=0.301

## 5m/target_4class
- steps: 460, high(>0.60): 195, low: 265, high_rate: 0.424
- HIGH: acc=0.753, dir_acc=0.876, cross_dir_err=0.124, true_up=0.448, pred_up=0.453, fold_mean=1.58
- LOW: acc=0.389, dir_acc=0.631, cross_dir_err=0.369, true_up=0.508, pred_up=0.461, fold_mean=2.01
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f1_v2_t6: wins=17, high=12 (0.706), uplift=0.282, dir_acc=0.875, pred_up=0.485
  - f1_v1_t5: wins=18, high=11 (0.611), uplift=0.187, dir_acc=0.720, pred_up=0.538
  - f2_v1_t3: wins=10, high=6 (0.600), uplift=0.176, dir_acc=0.819, pred_up=0.267
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f2_v2_t10: wins=8, high=1 (0.125), uplift=-0.299, dir_acc=0.706, pred_up=0.471
  - f3_v2_t10: wins=5, high=1 (0.200), uplift=-0.224, dir_acc=0.613, pred_up=0.321
  - f3_v3_t9: wins=5, high=1 (0.200), uplift=-0.224, dir_acc=0.671, pred_up=0.383

## 5m/target_breakfree
- steps: 471, high(>0.60): 292, low: 179, high_rate: 0.620
- HIGH: acc=0.800, dir_acc=0.852, cross_dir_err=0.068, true_up=0.421, pred_up=0.450, fold_mean=1.43
- LOW: acc=0.425, dir_acc=0.502, cross_dir_err=0.299, true_up=0.327, pred_up=0.424, fold_mean=1.64
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f3_v3_t24: wins=5, high=4 (0.800), uplift=0.180, dir_acc=0.804, pred_up=0.562
  - f1_v4_t28: wins=30, high=23 (0.767), uplift=0.147, dir_acc=0.773, pred_up=0.465
  - f1_v2_t18: wins=28, high=21 (0.750), uplift=0.130, dir_acc=0.740, pred_up=0.379
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f2_v3_t21: wins=6, high=2 (0.333), uplift=-0.287, dir_acc=0.583, pred_up=0.375
  - f2_v2_t16: wins=5, high=2 (0.400), uplift=-0.220, dir_acc=0.574, pred_up=0.375
  - f2_v4_t32: wins=11, high=5 (0.455), uplift=-0.165, dir_acc=0.609, pred_up=0.244

## 15m/target_4class
- steps: 434, high(>0.60): 161, low: 273, high_rate: 0.371
- HIGH: acc=0.767, dir_acc=0.886, cross_dir_err=0.114, true_up=0.448, pred_up=0.439, fold_mean=1.63
- LOW: acc=0.389, dir_acc=0.618, cross_dir_err=0.382, true_up=0.522, pred_up=0.461, fold_mean=2.02
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f5_v2_t8: wins=7, high=5 (0.714), uplift=0.343, dir_acc=0.812, pred_up=0.286
  - f2_v1_t6: wins=11, high=6 (0.545), uplift=0.174, dir_acc=0.756, pred_up=0.608
  - f2_v2_t8: wins=19, high=10 (0.526), uplift=0.155, dir_acc=0.753, pred_up=0.586
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f4_v1_t5: wins=5, high=1 (0.200), uplift=-0.171, dir_acc=0.700, pred_up=0.525
  - f3_v1_t4: wins=9, high=2 (0.222), uplift=-0.149, dir_acc=0.660, pred_up=0.312
  - f1_v2_t6: wins=40, high=11 (0.275), uplift=-0.096, dir_acc=0.748, pred_up=0.491

## 15m/target_breakfree
- steps: 465, high(>0.60): 293, low: 172, high_rate: 0.630
- HIGH: acc=0.808, dir_acc=0.851, cross_dir_err=0.069, true_up=0.427, pred_up=0.450, fold_mean=1.37
- LOW: acc=0.427, dir_acc=0.498, cross_dir_err=0.322, true_up=0.304, pred_up=0.406, fold_mean=1.86
- Top configs over-indexed in HIGH bucket (min 5 wins):
  - f2_v3_t15: wins=10, high=9 (0.900), uplift=0.270, dir_acc=0.787, pred_up=0.662
  - f1_v4_t28: wins=25, high=21 (0.840), uplift=0.210, dir_acc=0.829, pred_up=0.480
  - f2_v3_t24: wins=5, high=4 (0.800), uplift=0.170, dir_acc=0.875, pred_up=0.225
- Top configs over-indexed in LOW bucket (min 5 wins):
  - f2_v2_t16: wins=11, high=4 (0.364), uplift=-0.266, dir_acc=0.517, pred_up=0.489
  - f2_v4_t28: wins=5, high=2 (0.400), uplift=-0.230, dir_acc=0.528, pred_up=0.287
  - f1_v3_t15: wins=27, high=15 (0.556), uplift=-0.075, dir_acc=0.705, pred_up=0.481

## Cross-Unit Aggregate
- Global HIGH count=1379, LOW count=1268, HIGH rate=0.521
- Mean directional_accuracy: HIGH=0.863, LOW=0.573
- Mean directional_cross_error: HIGH=0.085, LOW=0.344
- Mean fold_count: HIGH=1.53, LOW=1.95