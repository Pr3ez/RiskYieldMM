# Stage-1 Comparison Report

Latest fixed-data Stage-1 live runs vs previous completed pre-2026-04-15 baseline.

Artifacts: `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/stage1_run_comparison/20260420_002255`

## Scope

- `8h/B`: current=`stage1_catboost_8h_b_live` vs baseline=`stage1_catboost_8h_b_live_pre20260415_20260415_132257`
- `8h/C`: current=`stage1_catboost_8h_c_live` vs baseline=`stage1_catboost_8h_c_live_pre20260415_20260415_132257`
- `24h/B`: current=`stage1_catboost_24h_b_live` vs baseline=`stage1_catboost_24h_b_live_pre20260415_20260415_132257`
- `24h/C`: current=`stage1_catboost_24h_c_live` vs baseline=`stage1_catboost_24h_c_live_pre20260415_20260415_132257`
- `7d/B`: current=`stage1_catboost_7d_b_live` vs baseline=`stage1_catboost_7d_b_live_pre20260415_20260415_132257`
- `7d/C`: current=`stage1_catboost_7d_c_live` vs baseline=`stage1_catboost_7d_c_live_pre20260415_20260415_132257`

## Aggregate Summary

- Mean delta in step winner accuracy across roots: `-0.0172`
- Mean delta in row-level directional accuracy across roots: `-0.0008`
- Mean delta in quality-pass rate across roots: `-0.0719`

## 24h/B

- Current run completed: `2026-04-15T20:49:22.196062`
- Baseline run completed: `2026-04-02T04:18:36.142549`
- Mean winner accuracy: `0.5234` -> `0.5173` | delta `-0.0061`
- Mean winner macro F1: `0.2206` -> `0.2327` | delta `0.0121`
- Mean winner cross-direction error: `0.3014` -> `0.3167` | delta `0.0153`
- Quality-pass rate: `0.2520` -> `0.1840` | delta `-0.0680`
- Row accuracy on available winner-path batches: `0.5234` -> `0.5173` | delta `-0.0061`
- Row directional accuracy on available winner-path batches: `0.6986` -> `0.6833` | delta `-0.0153`
- Mean top-class probability on available winner-path batches: `0.4436` -> `0.4516` | delta `0.0081`
- Mean step runtime: `18.7290`s -> `21.5534`s | delta `2.8244`s
- Winner combo changed on `375` / `500` steps | rate `0.7500`
- Step winner accuracy comparison: current better `219`, worse `242`, same `39`
- Baseline top winners: `[{"action_key": "f2_v3_t9", "count": 110}, {"action_key": "f2_v2_t10", "count": 74}, {"action_key": "f2_v1_t3", "count": 68}, {"action_key": "f2_v2_t4", "count": 64}, {"action_key": "f7_v1_t4", "count": 54}]`
- Current top winners: `[{"action_key": "f2_v3_t9", "count": 92}, {"action_key": "f2_v1_t3", "count": 75}, {"action_key": "f2_v2_t4", "count": 74}, {"action_key": "f7_v1_t4", "count": 57}, {"action_key": "f2_v2_t8", "count": 55}]`

## 24h/C

- Current run completed: `2026-04-15T23:52:01.361750`
- Baseline run completed: `2026-04-02T06:42:56.889463`
- Mean winner accuracy: `0.4849` -> `0.4904` | delta `0.0055`
- Mean winner macro F1: `0.2363` -> `0.2538` | delta `0.0176`
- Mean winner cross-direction error: `0.3234` -> `0.3240` | delta `0.0006`
- Quality-pass rate: `0.1600` -> `0.1280` | delta `-0.0320`
- Row accuracy on available winner-path batches: `0.4849` -> `0.4904` | delta `0.0055`
- Row directional accuracy on available winner-path batches: `0.6766` -> `0.6760` | delta `-0.0006`
- Mean top-class probability on available winner-path batches: `0.4184` -> `0.4273` | delta `0.0089`
- Mean step runtime: `17.2904`s -> `21.8850`s | delta `4.5945`s
- Winner combo changed on `377` / `500` steps | rate `0.7540`
- Step winner accuracy comparison: current better `237`, worse `234`, same `29`
- Baseline top winners: `[{"action_key": "f2_v3_t9", "count": 91}, {"action_key": "f2_v2_t10", "count": 72}, {"action_key": "f2_v1_t3", "count": 69}, {"action_key": "f2_v1_t5", "count": 64}, {"action_key": "f2_v1_t6", "count": 57}]`
- Current top winners: `[{"action_key": "f2_v1_t3", "count": 88}, {"action_key": "f7_v1_t4", "count": 76}, {"action_key": "f2_v2_t8", "count": 63}, {"action_key": "f2_v3_t9", "count": 59}, {"action_key": "f2_v2_t4", "count": 59}]`

## 7d/B

- Current run completed: `2026-04-16T02:51:42.721401`
- Baseline run completed: `2026-04-02T09:09:11.663138`
- Mean winner accuracy: `0.6242` -> `0.5951` | delta `-0.0291`
- Mean winner macro F1: `0.2214` -> `0.2250` | delta `0.0035`
- Mean winner cross-direction error: `0.3026` -> `0.3468` | delta `0.0441`
- Quality-pass rate: `0.4235` -> `0.3118` | delta `-0.1118`
- Row accuracy on available winner-path batches: `n/a` -> `n/a` | delta `n/a`
- Row directional accuracy on available winner-path batches: `n/a` -> `n/a` | delta `n/a`
- Mean top-class probability on available winner-path batches: `n/a` -> `n/a` | delta `n/a`
- Mean step runtime: `51.5794`s -> `63.3771`s | delta `11.7978`s
- Winner combo changed on `137` / `170` steps | rate `0.8059`
- Step winner accuracy comparison: current better `63`, worse `103`, same `4`
- Baseline top winners: `[{"action_key": "f2_v3_t9", "count": 46}, {"action_key": "f2_v2_t10", "count": 35}, {"action_key": "f2_v1_t3", "count": 26}, {"action_key": "f2_v2_t4", "count": 16}, {"action_key": "f2_v1_t5", "count": 15}]`
- Current top winners: `[{"action_key": "f2_v3_t9", "count": 38}, {"action_key": "f2_v2_t4", "count": 25}, {"action_key": "f2_v2_t8", "count": 21}, {"action_key": "f2_v1_t6", "count": 18}, {"action_key": "f2_v1_t3", "count": 18}]`
- Row-level metric coverage: baseline available `0` / `170`, current available `0` / `170`
- Baseline missing batch sample: `[101, 102, 103, 104, 105, 106, 107, 108, 109, 110]`

## 7d/C

- Current run completed: `2026-04-16T05:56:17.552458`
- Baseline run completed: `2026-04-02T11:39:20.464704`
- Mean winner accuracy: `0.7323` -> `0.6530` | delta `-0.0793`
- Mean winner macro F1: `0.2371` -> `0.2299` | delta `-0.0072`
- Mean winner cross-direction error: `0.2118` -> `0.3020` | delta `0.0902`
- Quality-pass rate: `0.6118` -> `0.3941` | delta `-0.2176`
- Row accuracy on available winner-path batches: `n/a` -> `n/a` | delta `n/a`
- Row directional accuracy on available winner-path batches: `n/a` -> `n/a` | delta `n/a`
- Mean top-class probability on available winner-path batches: `n/a` -> `n/a` | delta `n/a`
- Mean step runtime: `52.9569`s -> `65.1023`s | delta `12.1454`s
- Winner combo changed on `139` / `170` steps | rate `0.8176`
- Step winner accuracy comparison: current better `40`, worse `117`, same `13`
- Baseline top winners: `[{"action_key": "f2_v1_t3", "count": 43}, {"action_key": "f2_v2_t10", "count": 35}, {"action_key": "f2_v3_t9", "count": 29}, {"action_key": "f2_v1_t5", "count": 18}, {"action_key": "f2_v1_t6", "count": 17}]`
- Current top winners: `[{"action_key": "f2_v3_t9", "count": 37}, {"action_key": "f2_v1_t3", "count": 36}, {"action_key": "f7_v1_t4", "count": 25}, {"action_key": "f2_v2_t4", "count": 20}, {"action_key": "f2_v1_t6", "count": 16}]`
- Row-level metric coverage: baseline available `0` / `170`, current available `0` / `170`
- Baseline missing batch sample: `[101, 102, 103, 104, 105, 106, 107, 108, 109, 110]`

## 8h/B

- Current run completed: `2026-04-15T15:33:31.864358`
- Baseline run completed: `2026-04-01T23:44:18.286321`
- Mean winner accuracy: `0.5168` -> `0.5218` | delta `0.0049`
- Mean winner macro F1: `0.2402` -> `0.2483` | delta `0.0081`
- Mean winner cross-direction error: `0.2945` -> `0.2815` | delta `-0.0130`
- Quality-pass rate: `0.2240` -> `0.2280` | delta `0.0040`
- Row accuracy on available winner-path batches: `0.5168` -> `0.5218` | delta `0.0049`
- Row directional accuracy on available winner-path batches: `0.7055` -> `0.7185` | delta `0.0130`
- Mean top-class probability on available winner-path batches: `0.3988` -> `0.3922` | delta `-0.0066`
- Mean step runtime: `15.5356`s -> `15.5942`s | delta `0.0586`s
- Winner combo changed on `283` / `500` steps | rate `0.5660`
- Step winner accuracy comparison: current better `205`, worse `161`, same `134`
- Baseline top winners: `[{"action_key": "f2_v1_t3", "count": 74}, {"action_key": "f2_v2_t10", "count": 70}, {"action_key": "f2_v3_t9", "count": 66}, {"action_key": "f2_v2_t4", "count": 63}, {"action_key": "f2_v1_t6", "count": 59}]`
- Current top winners: `[{"action_key": "f2_v3_t9", "count": 69}, {"action_key": "f2_v1_t6", "count": 68}, {"action_key": "f2_v1_t3", "count": 68}, {"action_key": "f2_v2_t10", "count": 64}, {"action_key": "f2_v2_t4", "count": 62}]`

## 8h/C

- Current run completed: `2026-04-15T17:49:28.788578`
- Baseline run completed: `2026-04-02T01:42:17.542657`
- Mean winner accuracy: `0.5258` -> `0.5265` | delta `0.0008`
- Mean winner macro F1: `0.2400` -> `0.2399` | delta `-0.0001`
- Mean winner cross-direction error: `0.2803` -> `0.2805` | delta `0.0003`
- Quality-pass rate: `0.2440` -> `0.2380` | delta `-0.0060`
- Row accuracy on available winner-path batches: `0.5258` -> `0.5265` | delta `0.0008`
- Row directional accuracy on available winner-path batches: `0.7197` -> `0.7195` | delta `-0.0002`
- Mean top-class probability on available winner-path batches: `0.4002` -> `0.4043` | delta `0.0041`
- Mean step runtime: `14.0793`s -> `16.2424`s | delta `2.1631`s
- Winner combo changed on `270` / `500` steps | rate `0.5400`
- Step winner accuracy comparison: current better `190`, worse `172`, same `138`
- Baseline top winners: `[{"action_key": "f2_v2_t10", "count": 73}, {"action_key": "f2_v3_t9", "count": 69}, {"action_key": "f7_v1_t4", "count": 65}, {"action_key": "f2_v1_t6", "count": 63}, {"action_key": "f2_v2_t8", "count": 62}]`
- Current top winners: `[{"action_key": "f2_v3_t9", "count": 75}, {"action_key": "f2_v1_t3", "count": 71}, {"action_key": "f2_v2_t8", "count": 70}, {"action_key": "f2_v2_t10", "count": 61}, {"action_key": "f2_v1_t6", "count": 60}]`
