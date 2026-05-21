# Deep Review of Four-Class Labeling and Real-Time Signal Sizing in RiskYieldMM

## Executive summary

The active four-class labeling logic in **Pr3ez/RiskYieldMM** is implemented primarily in `scripts/feature_engineering/htf_multiregime_pipeline.py` and `scripts/feature_engineering/htf_kernels.py`. The current workflow constructs **offline labels** for `1m / target_4class` by joining each entry row to a **future label window**, computing forward-looking `close_end`, forward hybrid distance metrics from future `15m` bars, and then mapping those metrics into four classes: `DOWN_BALANCED`, `DOWN_EXPANSION`, `UP_BALANCED`, and `UP_EXPANSION`. The active policy is `opposite_family_first_half`, meaning B-family entries are labeled from the next C-family first half, and vice versa. This is a valid supervised-learning target construction scheme, but it is **not** prediction-time information and therefore must remain strictly label-only. The repo’s own feature-policy and optimizer code appear to preserve that separation. fileciteturn18file0 fileciteturn22file0 fileciteturn23file0 fileciteturn24file0 fileciteturn39file0

The strongest technical weakness is not “future data exists in labeling” — that is expected — but that the current four-class logic is **semantically noisy for live trading**. In `compute_4class_labels`, the “EXPANSION” classes fire whenever direction is up or down **and either upside-risk or downside-risk is high**. That collapses very different situations into the same class: continuation-type expansion and reversal-type expansion both map to the same label. For a live signal engine and position sizer, that reduces interpretability and weakens the mapping from predicted class to tradable edge. Fixed global thresholds such as `breakout_threshold=2.1`, `risk_ratio=2.5`, and `breakfree_threshold_1m=0.001` also make the label brittle across assets and regimes. fileciteturn22file0 fileciteturn18file0

On the feature side, the repo is in materially better shape. The audited HTF workflow states that model-facing features are mostly causal, that higher-timeframe broadcasts are availability-aware, and that label-only future columns are excluded from optimized/helper outputs. The critical live convention is explicit: the current `1m` bar’s OHLCV-derived features are only reproducible **after the bar closes**; they are not valid for bar-open inference. Auxiliary streams such as open interest, long/short ratio, and funding are treated with timestamp-role semantics (`available_at`, `settlement_at`) and are aligned through availability-aware joins. fileciteturn24file0 fileciteturn34file0 fileciteturn35file0

The most implementable upgrade is to keep the repo’s strong temporal contract and replace the current class rule with a label that is more directly tied to tradable outcomes. The most practical options are: a **volatility-normalized fixed-horizon four-class label** or a **triple-barrier-derived four-class label**. For live deployment, I would pair that with **meta-labeling**, **probability calibration**, and a **position-sizing layer** based on expected utility or fractional Kelly, always capped by volatility targeting and hard exposure limits. There is good support in the literature for volatility-managed sizing, risk-budgeting/risk-parity concepts, fractional-Kelly-style bet sizing, and multiple-testing-aware evaluation such as the Deflated Sharpe Ratio and Model Confidence Set procedures. citeturn8view0turn8view2turn11academia0turn17academia2turn17academia3

## Repository findings

The active implementation surface is concentrated and fairly readable. The table below lists the primary files that implement, constrain, or consume the current four-class target.

| File | Role in current logic | Key functions / objects | Inputs | Outputs | Why it matters |
|---|---|---|---|---|---|
| `scripts/feature_engineering/htf_kernels.py` | Core label math | `compute_distance_metrics`, `compute_hybrid_distance_metrics`, `_compute_past_distance_metrics`, `compute_4class_labels` | entry close, future highs/lows, batch ids, 15m positions, thresholds | future-distance statistics, `target_4class`, `target_name` | This is the direct four-class decision rule. fileciteturn21file0 fileciteturn22file0 |
| `scripts/feature_engineering/htf_multiregime_pipeline.py` | Orchestrates active label generation | `MultiRegimeHTFConfig`, `_build_15m_metrics`, `_build_1m_labels`, `_build_feature_batches` | combined 1m/15m HTF batches, family windows, thresholds, label-window policy | per-batch label parquet files, distance metrics, model-facing features | This file decides which future window is used and how labels are gated. fileciteturn18file0 fileciteturn38file0 fileciteturn39file0 |
| `scripts/feature_engineering/htf_feature_acceptance.py` | Feature/label boundary | `FINAL_OUTPUT_LABEL_ONLY_COLUMNS`, `get_final_output_forbidden_columns` | final-output schemas | blocked label-only columns and exclusion rules | This is the main anti-leakage guard for optimized/helper outputs. fileciteturn23file0 |
| `scripts/feature_engineering/optimize_htf_features.py` | Optimizer training contract | `load_early_batches`, `get_feature_cols` | feature batches + label batches | `X`, `y`, filtered feature columns | Confirms that only `timestamp`, `batch_id`, and the selected target are joined, not future label diagnostics. fileciteturn29file0 fileciteturn31file0 |
| `scripts/feature_engineering/compute_htf_features.py` | Prediction-time data availability contract | `source_available_timestamps`, `DATA_SOURCE_PATTERNS`, `HTFFeatureEngine` | source timestamps and availability metadata | causal feature alignment | Establishes when auxiliary features are visible to the model. fileciteturn34file0 fileciteturn35file0 |
| `docs/validation/htf-feature-helper-temporal-audit-2026-05-05.md` | Repository self-audit | temporal audit findings | pipeline outputs and tests | causality assessment | High-value evidence about what is live-safe vs label-only. fileciteturn24file0 |
| `FEATURE_AND_DATASET_SNAPSHOT.md` | Schema inventory | feature group inventory and representative label rows | local artifacts | examples of label/model-facing schemas | Best concise inventory of feature families and target semantics. fileciteturn25file0 fileciteturn26file0 |

The current active label semantics are as follows:

| Class | Name | Current repo meaning | Required future data to assign label | Available at prediction time |
|---:|---|---|---|---|
| 0 | `DOWN_BALANCED` | Downward directional label with no “high-risk” expansion flag | future `15m` lows/highs, future-window averages, batch/window alignment | No |
| 1 | `DOWN_EXPANSION` | Downward directional label with at least one expansion flag | same as above | No |
| 2 | `UP_BALANCED` | Upward directional label with no expansion flag | same as above | No |
| 3 | `UP_EXPANSION` | Upward directional label with at least one expansion flag | same as above | No |
| -1 | ignored row | Outside valid entry window or insufficient future bars | label-window completeness and remaining future bars | Not applicable |

This behavior comes directly from `compute_4class_labels`, which infers direction from future distance metrics and then marks “expansion” when either of the future-side risk flags is true. `_build_1m_labels` then gates labels to active entry rows only. fileciteturn22file0 fileciteturn39file0

A subtle but important assumption is the active **window policy**. The legacy target-labeling document clearly says the current workflow uses **`opposite_family_first_half`**: B entries are labeled from the next C first-half window and C entries from the next B first-half window, resolved by family-period start rather than a naïve sequential batch number. That design is sensible for learning “what happens next,” but it also means the target is explicitly about a future half-window, not the current bar or current batch remainder in a generic sense. fileciteturn27file0 fileciteturn39file0

## Prediction-time availability

The repo’s strongest design choice is that it draws a sharp boundary between **causal model inputs** and **future-only label artifacts**. The audit states that the workflow is aligned with the active `1m / target_4class` path, that rolling transforms are chronological, and that optimized/helper artifacts do not include label-only future fields. It also states explicitly that the current inference convention is **after the current 1m bar closes**. fileciteturn24file0

The practical availability contract for the main feature groups is:

| Feature family | Examples | Lookback / lag requirement | Prediction-time usable | Notes |
|---|---|---|---|---|
| Current-bar OHLCV and direct transforms | `open`, `high`, `low`, `close`, `volume`, `M_P_logReturn_pct` | current **closed** 1m bar plus trailing bars | Yes, after bar close | Not valid for bar-open prediction. fileciteturn24file0 fileciteturn25file0 |
| Rolling technical features | RSI, stochastic, ATR%, return std, Bollinger `%B`, ADX, CCI, z-scores, Sharpe/Sortino-like rolling measures | trailing windows; audit reports 1m windows of 60/120/240/480 and optimizer windows 240/480/960 | Yes | Backward-looking rolling operators only. fileciteturn24file0 |
| Past distance features | `D_dist_bot5_low_w120`, and similar `D_dist_*_wN` features | past-only windows via `_compute_past_distance_metrics` | Yes | These are causal analogs of the forward distance metrics used in labeling. fileciteturn21file0 fileciteturn38file0 |
| Auxiliary market-state features | mark/index/premium, OI, long/short ratio, funding features | available when source timestamp is usable | Yes, if availability timestamp has elapsed | `open_interest` and `long_short_ratio` are `available_at`; `funding_rate` is `settlement_at`; availability-aware alignment is used. fileciteturn34file0 fileciteturn35file0 |
| Cross/interactions | OI-return pressure, basis-return pressure, funding-basis pressure | depends on upstream causal inputs being available | Yes | Usability depends on upstream source visibility, not on future path. fileciteturn25file0 fileciteturn34file0 |
| Helper-model features | OU, GARCH, CUSUM, change-point, Kalman, EGARCH families | prior fitted state or bounded replay context | Yes, with correct live state contract | Audit says helper fits are causal; some helpers require context replay, others streaming handoff. fileciteturn24file0 |
| Regime/meta timing fields | `bar_in_batch_norm`, `batch_family`, `family_period_start`, `entry_window_hours` | timestamp-local metadata | Yes | Useful for a live router and position limits. fileciteturn18file0 fileciteturn37file0 |
| Label-only fields | `target_4class`, `target_breakfree`, `target_name`, `close_end`, `end_return`, `remaining_bars`, `dist_avg_*`, `dist_top5_high`, `dist_bot5_low`, `bar_pos_15m` | require future window or label construction pass | No | Explicitly marked label-only in policy. fileciteturn23file0 |

There are also a few explicit exclusions worth preserving. `htf_feature_acceptance.py` blocks `D_dist_avg_high_w240`, `D_dist_avg_low_w240`, and `D_dist_top5_high_w240` from final optimized/helper outputs because their warmup behavior is structurally incompatible with the saved front-half 1m rows, and it excludes certain EGARCH helper parameters as degenerate in the current helper contract. Those are not lookahead violations; they are **quality-control exclusions**. fileciteturn23file0

The repo’s own feature inventory shows a broad, prediction-time-usable feature set covering momentum, volatility, liquidity, normalized context, derivatives, funding, sentiment, binary patterns, candle structure, cross interactions, and helper-model features. The current `8h/B` helper-enriched schema is documented as 187 columns, with 123 base engineered features and 41 helper features. fileciteturn25file0 fileciteturn26file0

## Leakage assessment

The current labeling logic **absolutely uses unavailable lookahead data** — but in the right place: the label-generation stage. In `compute_distance_metrics`, the code explicitly walks from the current row to later rows in the same batch and stores future highs and lows from `i + 1` onward before computing average and tail distances. In `compute_hybrid_distance_metrics`, the code does the same for the future `15m` label window. `_build_1m_labels` then computes `close_end` from the label window, forms `end_return`, computes hybrid future-distance metrics, and only after that calls `compute_4class_labels`. Those values are not knowable at prediction time. fileciteturn21file0 fileciteturn22file0 fileciteturn38file0 fileciteturn39file0

That said, the evidence I found points to **no confirmed leakage into model-facing `X`** in the active HTF workflow. The feature acceptance policy explicitly lists all future-only columns as forbidden label-only fields. The optimizer’s `get_feature_cols` removes those label-only columns from transformable features, and `load_early_batches` joins feature batches to labels on only `timestamp`, `batch_id`, and the selected target column. The temporal audit further reports that sampled optimized/helper outputs had no label-only fields present and that the optimizer’s rolling transform is chronological. fileciteturn23file0 fileciteturn29file0 fileciteturn31file0 fileciteturn24file0

The larger issue is **semantic leakage / label noise**, not feature leakage. Specifically, `compute_4class_labels` defines `UP_EXPANSION` when `is_up` and `(high_risk_up | high_risk_down)`, and `DOWN_EXPANSION` when `~is_up` and `(high_risk_up | high_risk_down)`. That means a row can be labeled “up expansion” because the upside tail is strong **or because the downside tail is dangerous**, and likewise for the down class. For live trading and position sizing, those are qualitatively different states and should not normally share one sizing policy. fileciteturn22file0

Another important live-parity caveat is the prediction timestamp convention. The audit explicitly states that row-level OHLCV features are live-safe only if prediction happens **after the current bar has closed**. If you try to deploy the current feature set at bar open or intra-bar, you would introduce a real leakage / non-reproducibility problem even though the backtest pipeline itself is causal. fileciteturn24file0

A final gap is that the downstream operating-point logic I inspected emphasizes **directional accuracy and coverage**, not an explicit cost-adjusted utility or PnL objective. The final artifact fields in the downstream regime-analysis pipeline refer to “safe accuracy” and “coverage,” which is useful for classification control, but it is not yet a full position-sizing framework. fileciteturn11file0

## Method survey

No single labeling or sizing method is universally “best.” In the literature and in deployable practice, the winners tend to be the methods that keep the **ex-ante information set clean**, map more directly to **tradable outcomes**, and remain robust after **costs, class imbalance, and overlapping horizons** are handled properly. Below is the most practical short list for this repo.

### Labeling methods

| Method | Core idea | Ex-ante data needed | Main strengths | Main weaknesses | Real-time suitability | Key sources |
|---|---|---|---|---|---|---|
| Fixed-horizon thresholding | Label by sign/magnitude of return over a fixed future horizon | price at `t`, chosen horizon `H`, threshold | Simple, fast, interpretable | Sensitive to volatility regime and threshold choice; class imbalance can be severe | High | Repo-compatible as a direct replacement; see current fixed-threshold style in config and label pipeline. fileciteturn18file0 fileciteturn39file0 |
| Volatility-normalized fixed horizon | Label by future return divided by **past-only** volatility estimate | price at `t`, horizon `H`, past vol estimate `σ_t` | Much better cross-regime comparability; ties class magnitude to tradable edge | Requires careful volatility estimator and neutral-zone design | Very high | Volatility-managed scaling is well supported in the literature and improves risk-adjusted deployment behavior. citeturn8view0 |
| Triple-barrier event labeling | Use PT, SL, and vertical barrier; label by first hit or by terminal sign if no hit | ex-ante barrier distances and vertical horizon | Better aligned to trading exits and stop logic; cost-aware by construction | More implementation complexity; overlap/embargo handling matters | Very high | Common AFML-style practice; in this pass I did not retrieve a primary paper page, so implementation details should be validated before coding. |
| Regime-window labeling | Use a structurally meaningful future window, such as repo’s opposite-family first half | timestamp/family regime definition known at `t` | Fits the repo’s architecture and business logic well | Current class semantics are noisy because continuation and reversal tails are collapsed | Medium to high, if class rule is improved | Current repo implementation. fileciteturn27file0 fileciteturn39file0 |
| Meta-labeling | Predict whether to act on a base directional signal | base model output, ex-ante features, realized post-trade outcome during training | Strong for filtering low-quality signals and improving precision | Requires a reasonably good primary signal first | Very high | Common production pattern; primary-source retrieval for AFML meta-labeling was incomplete in this pass. |

### Position-sizing methods

| Method | Core idea | Ex-ante data needed | Main strengths | Main weaknesses | Real-time suitability | Key sources |
|---|---|---|---|---|---|---|
| Probability threshold + abstain | Trade only when calibrated class probability or margin exceeds threshold | calibrated probabilities | Very simple and robust | Leaves sizing suboptimal if all signals use same notional | Very high | Compatible with repo’s current accuracy/coverage operating-point style. fileciteturn11file0 |
| Expected-value / utility sizing | Convert class probabilities to expected return and expected variance, then size by utility | calibrated class probs, class-conditional return table, risk aversion | Directly ties size to forecast edge | Needs probability calibration and reliable payoff table | Very high | Markowitz-style mean-variance logic remains the standard utility baseline. citeturn12academia10 |
| Volatility targeting | Scale gross exposure inversely to forecast or realized volatility | `σ_t`, target portfolio vol | Strong empirical support; easy to cap risk | Can create turnover and leverage spikes if unsmoothed | Very high | Moreira and Muir show strong gains from volatility management. citeturn8view0 |
| Risk parity / risk budgeting | Allocate capital so risk contributions, not capital amounts, are balanced | covariance / vol estimates across assets | Natural for multi-asset deployment; stabilizes aggregate risk | Needs multi-asset covariance estimates and can be unstable in correlation breaks | High for multi-asset, low for single-asset alone | Roncalli’s risk-budgeting framework is a sound portfolio overlay. citeturn11academia0turn11academia2 |
| Kelly / fractional Kelly | Size proportional to estimated edge and payoff asymmetry | hit probability, payoff ratio, loss ratio | Theoretically attractive for growth-optimal sizing | Extremely sensitive to estimation error; full Kelly is too aggressive in practice | Medium unless fractional and capped | Kelly-style sizing originates in the classic 1956 framework and is usually safer in fractional form. citeturn2academia4turn6search1 |
| Deflated / multiple-testing-aware model selection | Not a sizing rule itself, but protects against choosing a false winner | full set of tried strategies | Essential when many labeling/sizing variants are tested | Requires disciplined experiment logging | High | The Deflated Sharpe Ratio was designed for exactly this problem. citeturn8view2 |

My practical ranking for this repo is:

**Best immediate label upgrade:** volatility-normalized fixed-horizon or triple-barrier-derived four-class labels.

**Best immediate sizing upgrade:** calibrated expected-value sizing or fractional-Kelly-over-utility sizing, always multiplied by a volatility target and hard caps.

**Best portfolio overlay if you go multi-asset:** risk-budgeting / risk-parity on top of per-asset signed target weights.

## Recommended redesign

The repo already has a good temporal skeleton. I would not throw that away. I would change the **class rule** and add a **real-time sizing layer**.

### Recommended target redesign

The cleanest upgrade is to keep the current **opposite-family window** but reinterpret the four classes through **magnitude and exit logic**, not through ambiguous tail flags.

A robust option is a **triple-barrier-derived four-class target**:

| New class | Suggested definition |
|---|---|
| `0 DOWN_BALANCED` | Lower barrier not hit first; vertical barrier reached; terminal normalized return is negative and moderate |
| `1 DOWN_EXPANSION` | Lower barrier hit first before vertical barrier |
| `2 UP_BALANCED` | Upper barrier not hit first; vertical barrier reached; terminal normalized return is positive and moderate |
| `3 UP_EXPANSION` | Upper barrier hit first before vertical barrier |
| `-1` | No-trade / ambiguous / insufficient data |

The key improvement is that “EXPANSION” becomes **a true event category** — an aggressive move that actually hit an ex-ante barrier — instead of a catch-all bucket that can currently mean either continuation or reversal risk. Barrier widths should be set with **past-only volatility**, for example `pt = k_up * σ_t` and `sl = k_dn * σ_t`, where `σ_t` is estimated only from trailing data available at the decision time. This keeps the label economically interpretable and real-time compatible. Moreira and Muir’s volatility-managed evidence supports making risk decisions relative to current volatility rather than fixed global thresholds. citeturn8view0

An even simpler transitional version is a **volatility-normalized horizon label**:

\[
z_t=\frac{r_{t,H}}{\sigma_t}
\]

with a neutral zone and two directional magnitudes. That preserves a four-class structure while removing the most ambiguous part of the current logic.

### Recommended sizing redesign

For live use, I would separate **direction**, **expansion confidence**, and **capital size**.

A workable real-time policy:

1. Compute class probabilities from the classifier.
2. Collapse into directional probabilities:
   - `p_up = p(class 2) + p(class 3)`
   - `p_down = p(class 0) + p(class 1)`
3. Estimate expected normalized return from historical class conditional means:
   - `mu_hat = Σ p_k * mean_norm_return_k`
   - `var_hat = Σ p_k * var_norm_return_k`
4. Apply a utility-based weight:
   - `w_utility = mu_hat / (gamma * max(var_hat, var_floor))`
5. Apply volatility target:
   - `w_vol = target_vol / max(sigma_t, sigma_floor)`
6. Optional fractional Kelly overlay:
   - `w_kelly = k_frac * kelly_estimate`
7. Final size:
   - `w = clip(w_utility * w_vol, -w_max, w_max)`
   - optionally blend with `w_kelly`
8. Trade only if calibrated confidence exceeds a no-trade threshold.

This is much more stable than directly mapping class ID to a fixed position size, and it uses only quantities that can be known at prediction time.

### Concrete code changes

The highest-value edits are:

| File | Suggested change | Why |
|---|---|---|
| `scripts/feature_engineering/htf_kernels.py` | Add `compute_4class_labels_volscaled(...)` and `compute_4class_labels_triple_barrier(...)` alongside the current `compute_4class_labels(...)` | Keeps legacy path intact while enabling A/B tests. Approximate anchor: the `compute_4class_labels` region currently fetched from the ~320+ area. fileciteturn22file0 |
| `scripts/feature_engineering/htf_multiregime_pipeline.py` | In `_build_1m_labels`, compute ex-ante `sigma_t` from trailing 1m returns before calling the labeler; swap the current class rule for the new function behind a config flag such as `label_method` | This is where the future label window is already assembled, so it is the correct insertion point. Approximate anchor: the `_build_1m_labels` block in the ~2450+ region. fileciteturn39file0 |
| `scripts/feature_engineering/htf_feature_acceptance.py` | Extend `FINAL_OUTPUT_LABEL_ONLY_COLUMNS` with any new diagnostics such as `sigma_entry`, `pt_hit_ts`, `sl_hit_ts`, `vertical_barrier_ts`, `event_return_norm`, `label_method` | Prevents accidental leakage from richer label diagnostics. fileciteturn23file0 |
| `scripts/feature_engineering/optimize_htf_features.py` | Allow new target names in config and metadata; keep join contract unchanged | Minimal plumbing change; the anti-leakage contract is already sound. fileciteturn29file0 fileciteturn31file0 |
| new module, e.g. `scripts/live/realtime_signal_sizer.py` | Add production-facing `score_signal(...)`, `size_position(...)`, and `cap_by_risk_budget(...)` | The inspected files do not yet show a dedicated production sizer. |

### Pseudocode

```python
# offline labeling at time t, after current 1m bar has closed
sigma_t = trailing_realized_vol(close, lookback=120)   # past-only
pt = close_t * (1 + k_up * sigma_t)
sl = close_t * (1 - k_dn * sigma_t)
t_vert = label_window_end_t

if future_high_until(t_vert) >= pt and first_hit_is_pt:
    y = 3  # UP_EXPANSION
elif future_low_until(t_vert) <= sl and first_hit_is_sl:
    y = 1  # DOWN_EXPANSION
else:
    z = (close_at(t_vert) / close_t - 1.0) / max(sigma_t, sigma_floor)
    if z >= theta_mid:
        y = 2  # UP_BALANCED
    elif z <= -theta_mid:
        y = 0  # DOWN_BALANCED
    else:
        y = -1  # abstain / ambiguous
```

```python
# live signal sizing
p = model.predict_proba(x_t)
p_up = p[2] + p[3]
p_down = p[0] + p[1]
edge = p_up - p_down

if abs(edge) < edge_threshold:
    target_weight = 0.0
else:
    mu_hat = sum(p[k] * class_mean_return[k] for k in range(4))
    var_hat = sum(p[k] * class_var_return[k] for k in range(4))
    w_utility = mu_hat / (gamma * max(var_hat, var_floor))
    w_vol = target_vol / max(sigma_t, sigma_floor)
    target_weight = clip(w_utility * w_vol, -w_max, w_max)
```

### Real-time data flow

```mermaid
flowchart LR
    A[Closed 1m bar at time t] --> B[Update causal features]
    B --> C[Align auxiliary sources only if available_at or settlement_at <= t]
    C --> D[Build model input x_t]
    D --> E[Predict class probabilities]
    E --> F[Collapse to directional edge and expansion confidence]
    F --> G[Apply calibration and no-trade threshold]
    G --> H[Size by utility or fractional Kelly]
    H --> I[Scale by volatility target and hard risk caps]
    I --> J[Send order]
    J --> K[Offline later: compute future-window label for training only]
```

## Evaluation design

The right way to compare labels in this repo is to keep the **feature set fixed**, change only the **labeling and sizing rules**, and evaluate both the **classifier** and the **trading policy**.

The minimum experiment matrix should include:

| Dimension | Recommendation |
|---|---|
| Data source | Use the repo’s current HTF artifacts for `1m` model-facing rows, first on the active BTCUSDT path and then on any multi-asset roots if the same contract holds. The user did not specify a final asset universe. fileciteturn24file0 fileciteturn25file0 |
| Regimes | Evaluate separately for `8h`, `24h`, and `7d`, and separately for B and C families, because the horizon geometry changes materially. fileciteturn18file0 |
| Inference convention | After bar close only. Anything else changes the feature contract. fileciteturn24file0 |
| Label baselines | Current repo `target_4class`; volatility-normalized four-class; triple-barrier four-class; optional three-class + meta-labeling |
| Sizing baselines | fixed notional, threshold-only, utility sizing, utility + vol target, fractional Kelly + vol cap |
| Costs | Explicit exchange fee model, spread/slippage model, and latency assumption |

For model validation, I would use **contiguous walk-forward splits with purging / embargo**. The reason is that label windows overlap in time, especially under the opposite-family policy, so neighboring rows can share future outcome windows. A naïve random split or even a simple time split without embargo will overstate performance.

The evaluation stack should include both **prediction metrics** and **trading metrics**:

| Metric family | Recommended metrics | Why |
|---|---|---|
| Classification | macro F1, balanced accuracy, per-class precision/recall, confusion matrix | Current classes are imbalanced and semantically asymmetric |
| Probability quality | log loss, Brier score, expected calibration error, reliability curves | Position sizing depends on calibrated probabilities |
| Directional utility | directional accuracy on traded rows, coverage, expected edge per trade | Better matched to downstream signal selection |
| Trading outcomes | net return, Sharpe, Sortino, max drawdown, Calmar, turnover, hit rate, average trade, profit factor, realized vol vs target vol | Classification gains that do not survive fees or sizing are not useful |
| Stability | by regime, by family, by market phase, by asset | Prevents one-regime overfitting |

For inference on relative performance, I would use:

- **Diebold–Mariano-style predictive-accuracy tests** for pairwise out-of-sample loss comparisons. Recent forecasting literature still treats DM-type equal-predictive-ability testing as the basic pairwise comparison tool. citeturn17academia1turn17academia2
- **Model Confidence Set / Superior Predictive Ability-style procedures** when comparing many labeling/sizing variants, to reduce data-snooping risk in a model tournament. citeturn17academia3turn17academia2
- **Deflated Sharpe Ratio** for the final chosen live candidate, especially if many thresholds, label variants, or sizing policies are swept. That is exactly the use case Bailey and López de Prado targeted. citeturn8view2
- **Block bootstrap confidence intervals** for PnL, Sharpe, turnover, and drawdown differences, because returns and trade outcomes will be serially dependent.

One external benchmark is especially relevant here: volatility-managed portfolios. Moreira and Muir show that reducing exposure when volatility is high can materially improve risk-adjusted performance because volatility changes are not offset one-for-one by changes in expected returns. That makes volatility targeting a strong default overlay for any class-probability-based position sizer in this repo. citeturn8view0

## Open questions and limitations

A few details remain genuinely unspecified and should be treated as open design decisions rather than guessed facts.

The user did not specify the final **live universe**, **execution venue**, **fee/slippage model**, **latency assumption**, or whether live predictions are to be taken **strictly after bar close** or at some other time. The repo’s audited assumption is after-close inference, and changing that assumption would change what features are valid. fileciteturn24file0

I inspected the active HTF labeling surface, the feature/optimizer boundary, and the main temporal audit. I did **not** line-audit every experimental file under `prediction_analysis/*target4class*`, so any statement about the broader experimental analysis layer should be read as limited to the files and fragments retrieved in this pass. The evidence I did inspect strongly supports the conclusion that the **active** leakage boundary is under control, while the **economic alignment** of the current four-class target should be improved. fileciteturn11file0 fileciteturn24file0

I was also not able, in this pass, to retrieve a clean primary web source for every AFML-associated labeling concept, especially the original web-published references for **triple-barrier** and **meta-labeling**. I therefore described those two methods cautiously from standard practice and recommended validating the exact implementation details against your preferred primary source before coding them into the repo.