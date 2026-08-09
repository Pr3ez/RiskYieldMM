# The central problem

A profitable trading model should **not primarily try to predict the exact future stock price**.

It should estimate whether there is a sufficiently strong, tradable edge:

[
\text{Expected net edge}_t
==========================

## E[r_{t \rightarrow t+H}\mid X_t]

## \text{transaction costs}

\text{risk penalty}
]

Then it should trade only when that edge is meaningfully positive.

This distinction matters because:

* A model may predict price accurately but fail to cover fees and slippage.
* A model may have only 52% directional accuracy and still be profitable if winners are larger than losers.
* A model may have 80% accuracy and still lose money if it predicts the unimportant, small moves correctly but misses rare large losses.

The real objective is therefore:

> **Find a weak but repeatable conditional advantage, select only the best opportunities, size them safely, and execute them cheaply.**

---

# 1. Why stock prediction is unusually difficult

## 1.1 Returns contain very little predictable signal

Stock-price movements are dominated by information that was not known before the movement happened: news, order flow, macroeconomic surprises, earnings releases and changes in investor expectations.

Research on machine learning in asset pricing describes returns as having a low signal-to-noise ratio, with unpredictable news obscuring the smaller predictable component. It also found that relatively shallow neural networks and tree models could outperform deeper architectures, partly because financial datasets have less independent information than image or language datasets.

A useful simplification is:

[
r_{t+1} = \text{small predictable component} + \text{large unpredictable component}
]

Machine learning sees both. Unless the pipeline is carefully controlled, it usually learns the large noisy component.

---

## 1.2 Market relationships change over time

The data-generating process is not fixed.

For example:

* Momentum may work in one regime and reverse in another.
* Volatility changes.
* Correlations between assets change.
* Market participants discover and exploit anomalies.
* Regulations, market structure and transaction costs change.
* A feature may work before 2020 and become useless afterward.

Formally:

[
P(Y_{t+1}\mid X_t)
\neq
P(Y_{t+k+1}\mid X_{t+k})
]

This is called **non-stationarity**, **concept drift** or a **regime change**.

Research comparing time-series validation procedures found that when non-stationarity is present, out-of-sample evaluation preserving chronological order generally produces more realistic performance estimates than ordinary random cross-validation. ([arXiv][1])

---

## 1.3 Financial rows are not independent observations

In ordinary machine learning, rows are often treated as approximately independent.

Financial observations overlap.

Suppose every row predicts the next 24 hours:

```text
row t     target uses prices t → t+24
row t+1   target uses prices t+1 → t+25
row t+2   target uses prices t+2 → t+26
```

These targets share almost the same future price path.

Therefore, 100,000 rows may contain substantially fewer than 100,000 independent prediction examples.

This creates:

* exaggerated confidence;
* nearly duplicated labels;
* leakage between training and validation;
* unstable performance estimates.

---

## 1.4 Data leakage is extremely easy

A model can unknowingly receive future information through:

* global normalization;
* feature selection using the complete dataset;
* computing rolling windows before splitting;
* imputing missing values using future rows;
* overlapping label windows;
* revised fundamental data;
* using an asset universe based on companies that exist today;
* using closing prices before the close was actually known;
* computing a market-wide rank with securities unavailable at that time.

Leakage produces excellent validation scores and poor live performance. General research on ML leakage shows that preprocessing or feature-selection information from the evaluation set can create overly optimistic performance estimates and destroy generalization. ([arXiv][2])

---

## 1.5 Backtest optimization creates false discoveries

Suppose you test:

* 500 feature combinations;
* 30 target definitions;
* 20 training lengths;
* 15 thresholds;
* 10 model configurations.

That is potentially millions of strategy variants.

Even if none contains real information, one variant may appear highly profitable by chance.

The probability of backtest overfitting increases as more configurations are evaluated and selected using historical performance. Standard holdout methods can also be unreliable when the same holdout is repeatedly consulted during strategy development. ([SSRN][3])

A recent 2026 preprint goes further and proposes testing the entire workflow against synthetic zero-predictability environments. Its central warning is valuable, although the paper is still a preprint: a workflow can generate apparently significant results because of preprocessing, model-selection and validation artifacts rather than genuine predictability. ([arXiv][4])

---

## 1.6 Accuracy is usually the wrong objective

Consider two models.

### Model A

* Accuracy: 70%
* Average correct trade: +0.1%
* Average incorrect trade: −0.5%
* Costs: 0.05%

[
EV = 0.70(0.1%) - 0.30(0.5%) - 0.05%
]

[
EV = -0.13%
]

It loses money despite 70% accuracy.

### Model B

* Accuracy: 45%
* Average winner: +1.0%
* Average loser: −0.4%
* Costs: 0.05%

[
EV = 0.45(1.0%) - 0.55(0.4%) - 0.05%
]

[
EV = +0.18%
]

It can be profitable despite being wrong more often than right.

Therefore:

[
\text{Profitability}
\neq
\text{classification accuracy}
]

---

# 2. Correct financial data preprocessing

The pipeline should begin by defining exactly what information exists at every decision time.

## Step 1: Define the prediction contract

Before creating features, specify:

```text
Decision time:        end of bar t
Latest usable data:   information published by time t
Entry:                open of bar t+1
Exit:                 close of bar t+H
Direction:            long, short or both
Estimated costs:      fees + spread + slippage + funding
Minimum edge:         return required before opening a trade
```

For example:

[
r_{t,H}
=

\frac{P^{exit}*{t+H}}{P^{entry}*{t+1}} - 1
]

A more realistic target is:

[
r^{net}_{t,H}
=============

## r_{t,H}

## \text{fees}

## \text{spread}

\text{slippage}
]

The entry should normally be the **next executable price**, not the same closing price used to construct the features.

---

## Step 2: Build point-in-time data

Every value must represent what was actually known at the historical decision time.

Check:

* exchange timestamps and time zones;
* duplicate candles;
* missing candles;
* stock splits and dividends;
* symbol changes;
* delisted securities;
* revised economic data;
* fundamental publication dates;
* delayed reporting;
* universe membership at each date;
* bid/ask information where available.

A crucial distinction is:

* Use adjusted data where appropriate for calculating historical returns and indicators.
* Use realistic unadjusted executable prices for simulated orders.
* Never let a later corporate-action adjustment create information that was unavailable historically.

---

## Step 3: Create causal features

At time (t), every feature must use only observations at or before (t).

Correct:

[
MA_{20,t}
=========

\frac{1}{20}
\sum_{i=0}^{19} P_{t-i}
]

Incorrect:

[
MA_{20,t}
=========

\frac{1}{20}
\sum_{i=-10}^{9} P_{t-i}
]

The second version includes future observations.

For each feature, document:

```text
source columns
lookback length
minimum required observations
publication delay
final lag applied
normalization method
```

Features should preferably be built using explicit causal expressions and then verified with timestamp tests.

---

## Step 4: Transform prices into more learnable quantities

Raw stock prices are usually poor direct features because their numerical level changes over time.

More useful transformations include:

### Returns

[
r_t = \ln\left(\frac{P_t}{P_{t-1}}\right)
]

### Volatility-normalized returns

[
z_t = \frac{r_t}{\sigma_t}
]

### Distance from a moving reference

[
d_t = \frac{P_t - MA_{20,t}}{\sigma_{20,t}}
]

### Relative volume

[
RVOL_t = \frac{Volume_t}{MedianVolume_{20,t}}
]

### Cross-sectional percentile

```text
momentum rank of this stock among all available stocks at time t
```

These quantities are generally more comparable across time and assets than raw price levels.

Do not automatically remove every extreme value. In finance, extreme observations may represent the most economically important events. Clipping thresholds should be estimated from the training period only, and the unclipped results should also be inspected.

---

## Step 5: Design a target that matches the intended action

There is no universally correct target.

The target should follow the eventual portfolio decision.

| Trading decision                                   | Suitable ML objective |
| -------------------------------------------------- | --------------------- |
| Predict approximate future return                  | Regression            |
| Predict whether an opportunity exceeds a threshold | Classification        |
| Select the best few opportunities in each batch    | Ranking               |
| Predict future risk                                | Volatility regression |
| Decide whether to accept another model’s signal    | Meta-classification   |

## Regression target

[
y_t = r^{net}_{t,H}
]

A stronger alternative is volatility-normalized return:

[
y_t
===

\frac{r^{net}_{t,H}}{\sigma_t\sqrt{H}}
]

This prevents high-volatility periods from automatically producing numerically larger targets.

## Classification target

For an upward model:

[
y^{up}*t =
\mathbb{1}
\left[
r^{net}*{t,H} > \tau^{up}_t
\right]
]

For a downward model:

[
y^{down}*t =
\mathbb{1}
\left[
-r^{net}*{t,H} > \tau^{down}_t
\right]
]

The threshold should normally account for:

* trading costs;
* current volatility;
* required reward-to-risk;
* minimum economically meaningful movement.

Separate up and down models are often sensible because upward and downward movements can have different distributions and predictors.

---

## Step 6: Consider path-dependent labels

A final return alone may hide what happened during the holding period.

For example:

```text
Entry: 100
Price falls to 90
Price later rises to 103
Final return: +3%
```

A target based only on the final price calls this successful, even though a realistic stop-loss may have closed the position at a large loss.

A path-aware target can ask:

```text
Did the take-profit level occur before the stop-loss level?
```

or use:

* maximum favourable excursion;
* maximum adverse excursion;
* time to target;
* volatility-adjusted barriers;
* realized return after simulated risk controls.

That makes the label closer to the actual trading strategy.

---

# 3. Correct train, validation and test splitting

## Never use ordinary random train-test splitting

Random splitting mixes past and future regimes and can place heavily overlapping observations in both training and validation.

Use chronological walk-forward validation.

```text
Fold 1:
Train       2016–2019
Embargo
Validation  2020

Fold 2:
Train       2017–2020
Embargo
Validation  2021

Fold 3:
Train       2018–2021
Embargo
Validation  2022
```

There are two major forms.

### Expanding window

```text
Train 1: [A]
Train 2: [A B]
Train 3: [A B C]
```

Useful when older data remains relevant.

### Rolling window

```text
Train 1: [A B]
Train 2: [B C]
Train 3: [C D]
```

Useful when older regimes become harmful.

Training-window length should itself be selected through validation, not assumed.

---

## Purge overlapping target intervals

Suppose a validation row predicts from January 10 to January 20.

Any training row whose target uses prices inside January 10–20 should be removed, even when its feature timestamp appears before validation.

Formally, remove a training example (i) when:

[
[t_i^{start}, t_i^{end}]
\cap
[t_{val}^{start}, t_{val}^{end}]
\neq \varnothing
]

This is the purpose of **purging**.

---

## Add an embargo

After the validation region, exclude an additional period before allowing training observations again.

This helps prevent information contamination caused by:

* long feature lookbacks;
* overlapping labels;
* delayed market effects;
* samples close to the validation boundary.

The embargo length should be based on the maximum feature and label dependency, not chosen arbitrarily.

---

## Use nested validation

A correct structure is:

```text
Outer walk-forward folds:
    estimate final out-of-sample performance

Inner walk-forward folds:
    select features
    tune parameters
    choose training length
    choose thresholds
```

The outer validation results must not repeatedly influence hyperparameter decisions.

Keep one final test period completely untouched until the complete pipeline has been frozen.

---

# 4. Every preprocessing operation belongs inside the fold

For each walk-forward fold:

1. Fit transformations using only the training portion.
2. Apply the fitted transformations to validation.
3. Never refit on validation.

This applies to:

* normalization;
* imputation;
* winsorization;
* PCA;
* feature selection;
* target encoding;
* clustering;
* regime detection;
* calibration;
* probability thresholds.

For example, this is wrong:

```python
scaler.fit(full_dataset)
train_scaled = scaler.transform(train)
validation_scaled = scaler.transform(validation)
```

This is correct:

```python
scaler.fit(train)
train_scaled = scaler.transform(train)
validation_scaled = scaler.transform(validation)
```

The same rule applies to feature importance. Selecting features using the complete dataset is leakage.

Tree models such as CatBoost generally do not need standard scaling, but clipping, missing-value handling, feature generation and feature selection still need to remain fold-local.

---

# 5. Evaluate predictions like a trading system

## Predictive metrics

Depending on the task:

* Spearman rank correlation;
* precision at (k);
* recall at (k);
* PR-AUC for rare positive events;
* Brier score or calibration error;
* NDCG for ranking;
* correlation between predicted and realized return;
* percentage of actionable windows with at least one correct signal.

## Economic metrics

Always calculate:

[
PnL_t =
Position_t \times Return_t - Costs_t
]

Then inspect:

* net Sharpe ratio;
* average net return per trade;
* maximum drawdown;
* drawdown duration;
* turnover;
* profit factor;
* exposure;
* tail losses;
* performance by year;
* performance by regime;
* capacity and market impact;
* sensitivity to higher costs.

A strategy is not robust because it has one strong aggregate Sharpe ratio.

A better result looks like:

```text
positive in most folds
not dependent on one year
not dependent on one asset
survives doubled costs
survives moderate parameter changes
works on untouched test data
degrades gradually rather than collapsing
```

---

# 6. How stronger ML trading systems address these problems

## 6.1 They predict an easier quantity

Exact price prediction is usually unnecessarily difficult.

Better targets include:

* relative performance against other stocks;
* volatility;
* probability of a large move;
* probability that a signal survives costs;
* return rank;
* downside risk;
* whether a trade should be rejected.

In many cases, predicting **which stock is better than another** is easier and more useful than predicting each exact return.

---

## 6.2 They use learning-to-rank when the decision is top-(k)

Your decision structure is approximately:

> From each prediction batch, select only a small number of the strongest opportunities.

That is a ranking problem.

For each decision batch (q):

```text
group_id = batch q
rows     = candidates available in batch q
target   = future net utility or ordinal relevance
output   = ranking score
```

Then:

```text
rank all candidates
select top k
trade only if score exceeds an abstention threshold
```

CatBoost ranking objectives generate comparisons within groups and support objectives based on ranking quality such as NDCG and pairwise ranking. ([catboost.ai][5])

This is often better aligned than classification because classification asks:

```text
Is each row positive independently?
```

Ranking asks:

```text
Which rows are best relative to the other currently available rows?
```

For your project, separate up and down rankers are a reasonable architecture:

```text
up ranker   → best long opportunities
down ranker → best short opportunities
```

But ranking only helps when groups represent real decision sets. Arbitrary groups would teach meaningless comparisons.

---

## 6.3 They allow “no trade”

A common mistake is forcing the model to predict long or short on every row.

A profitable system should often produce:

```text
No trade.
```

The decision can be:

[
Trade_t =
\begin{cases}
Long, & score^{up}*t > \tau*{up}\
Short, & score^{down}*t > \tau*{down}\
None, & \text{otherwise}
\end{cases}
]

Thresholds should be chosen using net economic performance on validation data, not accuracy.

The threshold can also depend on:

* volatility;
* liquidity;
* regime;
* uncertainty;
* recent model degradation;
* estimated trading costs.

---

## 6.4 They separate prediction from trade filtering

A useful two-stage system is:

### Stage 1: Alpha model

Predicts:

```text
direction
future return
relative rank
```

### Stage 2: Meta-model

Predicts:

```text
Should the proposed trade actually be accepted?
```

The meta-model can use:

* alpha-model score;
* uncertainty;
* current volatility;
* spread;
* liquidity;
* regime;
* expected holding time;
* distance from stop-loss;
* recent model reliability.

This allows the alpha model to find opportunities while the second model removes low-quality or expensive trades.

---

## 6.5 They are regime-aware without trusting regimes blindly

Regime variables can include:

* volatility level;
* volatility trend;
* market direction;
* cross-asset correlation;
* liquidity;
* dispersion;
* macroeconomic state.

Possible methods include:

* hidden Markov models;
* change-point detection;
* Gaussian mixtures;
* clustering;
* rolling quantile rules;
* supervised regime classification.

K-means can provide a useful descriptive regime feature, but it has limitations:

* it ignores temporal ordering;
* it assumes distance-based cluster geometry;
* cluster identities can change between retraining runs;
* it does not inherently estimate transition probability;
* a cluster does not automatically represent an economically meaningful regime.

Regime information is often safer as an additional feature or gating variable than as the entire trading strategy.

---

## 6.6 They combine complementary models

A sensible ensemble could contain:

```text
ElasticNet:
    stable sparse linear relationships

CatBoost:
    nonlinear interactions and thresholds

Shallow temporal CNN:
    local sequential patterns

Regime model:
    market-state context
```

Research comparing ML models for stock return prediction found useful gains from nonlinear interactions in trees and neural networks, but also found shallow networks more effective than deeper models in that particular low-signal asset-pricing setting.

The ensemble should combine models only when their errors are meaningfully different. Combining five nearly identical boosted-tree models provides less diversification than combining models with different inductive biases.

---

## 6.7 They optimize selection stability, not the best historical score

Instead of selecting the model with the highest average Sharpe, use an objective such as:

[
Score =
MedianFoldReturn
----------------

## \lambda_1 Turnover

## \lambda_2 Drawdown

\lambda_3 FoldInstability
]

You can also penalize:

* large train-to-validation degradation;
* zero-signal folds;
* concentration in one period;
* excessive feature count;
* sensitivity to small parameter changes.

A slightly weaker but stable model is usually preferable to one spectacular configuration surrounded by losing configurations.

---

## 6.8 They make execution part of the model

A prediction is not tradable unless it survives:

* bid-ask spread;
* commission;
* slippage;
* delayed execution;
* partial fills;
* borrow costs;
* funding;
* market impact.

Backtest assumptions should be deliberately pessimistic.

For example:

```text
Base costs
1.5 × costs
2.0 × costs
one-bar delayed entry
worse fill by half-spread
```

A strategy that disappears under a small cost increase probably has insufficient edge.

---

# 7. A suitable architecture for your current research

Given your batch-based extreme-up and extreme-down targets, a robust design would look like this:

```text
Raw OHLCV and contextual data
        ↓
Point-in-time cleaning
        ↓
Causal RPF / technical / regime features
        ↓
Volatility-normalized, cost-aware labels
        ↓
Purged walk-forward fold generator
        ↓
Fold-local feature filtering
        ↓
Separate long and short models
        ↓
Batch-level ranking
        ↓
Top-k plus abstention threshold
        ↓
Cost-aware position sizing
        ↓
Walk-forward portfolio simulation
        ↓
Locked final test
        ↓
Paper trading
        ↓
Live deployment with drift monitoring
```

## Suggested model roles

```text
ElasticNet
    baseline and noisy-feature filtering

CatBoostRanker UP
    rank strongest upward candidates within each batch

CatBoostRanker DOWN
    rank strongest downward candidates within each batch

Optional classifier
    reject low-confidence ranked signals

Optional temporal CNN
    summarize local sequence structure

Risk layer
    volatility scaling, exposure caps and correlation limits
```

## Suggested target for ranking

Within each batch:

[
utility_i =
\frac{future\ net\ return_i}
{expected\ volatility_i}
------------------------

\lambda \cdot adverse\ excursion_i
]

You can convert utility into ordinal levels:

```text
0 = poor
1 = neutral
2 = moderate
3 = strong
4 = exceptional
```

or use a continuous relevance target when supported by the selected ranking objective.

The ranking model should then be evaluated primarily on:

* precision among top (k);
* average net utility among top (k);
* NDCG;
* number of missed high-opportunity batches;
* number of empty-signal batches;
* turnover;
* net portfolio results.

That is substantially better aligned with your use case than global binary accuracy.

---

# 8. The strongest practical rule

A good trading ML system is usually not one brilliant model.

It is a conservative research process in which:

```text
Target alignment
+ causal data
+ leakage-resistant validation
+ selective predictions
+ realistic costs
+ stable risk management
```

matter more than replacing CatBoost with a larger neural network.

The model may supply only a small edge. The rest of the profitability comes from:

* not trading weak predictions;
* controlling losses;
* minimizing costs;
* sizing by risk;
* diversifying signals;
* detecting when the edge has stopped working.

There is no preprocessing method or model architecture that guarantees profitability. The most credible goal is a system whose edge remains positive across multiple genuinely unseen periods and under assumptions more pessimistic than expected live conditions.

Small language note: **finally** has two “l” letters, and **accurate** has two “c” letters.

[1]: https://arxiv.org/abs/1905.11744 "[1905.11744] Evaluating time series forecasting models: An empirical study on performance estimation methods"
[2]: https://arxiv.org/pdf/2311.04179 "ML pitfalls - arXiv - version 2"
[3]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253 "The Probability of Backtest Overfitting by David H. Bailey, Jonathan Borwein, Marcos Lopez de Prado, Qiji Jim Zhu :: SSRN"
[4]: https://arxiv.org/pdf/2604.15531 "Spurious Predictability in Financial Machine Learning"
[5]: https://catboost.ai/docs/en/concepts/loss-functions-ranking "Ranking: objectives and metrics | CatBoost"

# How to Turn Many Models Into Better Trading Decisions

## The core answer

Yes, trading decisions are usually better when they are based on the **outputs of multiple specialized models rather than one monolithic predictor**—but only when those models are **diverse in role, trained leakage-safely, and combined through a learned or rule-based decision layer that is itself validated out of sample**. In ensemble learning generally, combining estimators improves robustness when the members have complementary strengths, and stacking is specifically designed to learn how to combine base-model outputs using cross-validated predictions. In finance, the strongest results tend to come not from “more models” by itself, but from combining models that solve **different subproblems**: return ranking, volatility/risk, regime adaptation, implementability, and trade filtering. citeturn13view2turn13view0turn7view0turn7view1

A useful way to think about your current stack is that you already have a strong **state-description layer**. What you do **not** yet have, at least from what you listed, is the full **decision stack** that converts state into a tradeable, net-of-cost edge. The literature is very clear that this last part matters: machine-learning forecasts can look good statistically yet fail economically once costs, slippage, and overtrading are included. Recent evidence on hourly BTC/USDT forecasting, for example, found positive gross predictive value in XGBoost, LSTM, and iTransformer models, but naive sign-based trading failed once a 10 bp cost was imposed. Likewise, transaction-cost-aware portfolio research shows that the objective must “know” about implementability, or else the model will chase patterns that are not usable after frictions. citeturn7view11turn7view1turn4search10

## What your current stack already does well

Your indicators cover several of the exact signal families that the academic literature repeatedly finds important: **momentum or trend persistence, liquidity or participation, and volatility or risk state**. Gu, Kelly, and Xiu’s large comparative study found that the dominant predictive signals across machine-learning methods include “variations on momentum, liquidity, and volatility,” which maps closely to your CUSUM trend, EWMA volatility, comparable volatility, participation, prior structure, and cross-timeframe alignment layers. In other words, your current system is not missing the market-state basics; it already captures a serious amount of the information most return-prediction systems start from. citeturn7view0

More specifically, your CUSUM trend, vol-scaled trend, and cross-timeframe context are strong **state-estimation features** for persistence, path quality, and alignment; your comparable volatility and EWMA modules encode **risk regime state**; your participation and prior-structure modules give a useful read on **tradeability and location**. That is a sensible feature foundation because financial ML tends to benefit from nonlinear interactions among exactly these kinds of variables, especially in tabular settings. The important distinction is that these are still mostly **diagnostic features**, not yet a complete stack for turning “market state” into “trade now, size this much, and expect positive net utility.” citeturn7view0turn5search6

So, the honest assessment is this: your stack is already quite mature as a **market state engine**, but it still looks underpowered as a **decision engine**. The gap is not that you need ten more trend indicators. The gap is that you need additional layers for **expected net edge, cost/impact, uncertainty, trade filtering, and portfolio construction**. That is where most profitable systems differentiate themselves. citeturn7view1turn18view0turn7view11

## What is still missing

The most important missing layer is **implementability**. A signal is not a trade until you can estimate spread crossing, expected slippage, participation rate, and likely market impact. Research on implementable portfolios argues that the optimizer should be given explicit knowledge of transaction costs so it can favor “subtle but usable” patterns over stronger-looking but too-costly ones. Related work on trading volume shows that volume and participation rate are central to trading costs, and that overestimating available liquidity can be economically much worse than underestimating it. If you are not modeling this, your system is still missing one of the most practical parts of the puzzle. citeturn7view1turn18view0

The next missing layer is **uncertainty and abstention**. A profitable system should not just say “up” or “down”; it should know when the evidence is weak. Deep-ensemble research shows that ensembles can provide useful predictive uncertainty, and probability calibration research shows that raw classifier probabilities are often miscalibrated and should be post-calibrated on holdout data. In trading terms, that means your final system should include a “no trade” region when the models disagree, the probability is poorly calibrated, or estimated edge is too close to estimated cost. citeturn13view3turn7view9

You are also missing a more explicit **target-side model**. Your current stack describes trend, location, volatility, and participation, but I do not see an explicit model for one of the following: expected return over a fixed horizon, probability of hitting the take-profit before the stop, expected adverse excursion, expected slippage, or expected downside quantile. Risk-forecasting research has shown that nonlinear quantile models can materially improve Value-at-Risk forecasts, and realized-volatility research shows that sequence models can outperform traditional econometric baselines for volatility. A serious trading decision usually needs both an **opportunity model** and a **risk model**. citeturn17view0turn7view3

If you trade more than one asset or more than one setup at a time, you are probably also missing a **ranking layer**. Finance papers on learning to rank show that if the real decision is “which few candidates are best right now,” then regression-then-rank can be suboptimal because mean-squared-error training is not aligned with the portfolio choice. Cross-sectional stock-selection work shows that ranking models, especially pairwise and listwise approaches, can produce better rankings and better portfolio outcomes, and recent international evidence shows neural networks beat linear models more clearly in ranking-based portfolio construction than in raw forecasting. citeturn15view0turn7view4

A further omission is **event and jump awareness**. Many important returns are generated around earnings, macro releases, and abrupt information arrivals. Research on high-frequency jumps and machine-readable news finds that relevant public news quickly maps into price jumps, but also that the majority of jumps do not have identifiable public-news explanations. That means a practical model should either incorporate event/news features where feasible or explicitly down-weight or abstain during high-jump-risk windows, because pure price-based state models will sometimes be run over by information shocks they cannot infer from chart structure alone. citeturn7view2

Finally, I do not see a clear **portfolio and execution layer** in your description. Even a good signal can lose after aggregation if correlated bets pile up in the same direction, if turnover is too high, or if sizing is not tied to forecast quality and risk. Recent portfolio research shows that directly connecting prediction to implementable portfolio choice can outperform simple two-step pipelines; and deep momentum work shows there is value in learning signals jointly with risk-adjusted objectives rather than optimizing only point prediction. citeturn4search10turn7view6

## Which model families are best for which jobs

For your setup, the best approach is not “pick the one best model class.” It is to assign model classes to the tasks they are naturally good at.

A **sparse linear baseline** such as Elastic Net or logistic regression is still worth keeping. It gives you a stable benchmark, exposes fragile nonlinear claims, and is often harder to fool with small samples. This matters because even recent international evidence shows that when observations are limited, regression trees can underperform linear models; and recent factor-timing work warns that off-the-shelf deep nets overfit easily in finance because the signal-to-noise ratio is low and historical samples are short. citeturn7view4turn7view5

For your hand-engineered indicator set, **gradient-boosted trees** are the strongest default opportunity model. They are excellent on tabular data, handle nonlinear interactions naturally, and have a long record of strong performance in financial cross-sections. Gu, Kelly, and Xiu found that trees and neural networks were the best-performing return-prediction families in their setting because they captured nonlinear interactions missed by linear models. For state-heavy feature tables like yours, a CatBoost, LightGBM, or XGBoost-style model should usually be the first serious benchmark. citeturn13view2turn7view0

When the real decision is “pick the best few setups,” **learning-to-rank** is often more aligned than regression or classification. CatBoost’s ranking objectives explicitly optimize group-based pairwise or listwise structure, including NDCG-style targets, and finance-specific work on cross-sectional strategies shows that learning-to-rank can materially improve ranking accuracy and strategy Sharpe by better modeling relative orderings. If you trade among multiple symbols, multiple setups, or a batch of concurrent signal candidates, this is one of the most relevant model families you can add. citeturn13view4turn15view0

For **volatility and tail-risk**, sequence-aware or quantile-aware models are more natural than plain return predictors. Bucci found that recurrent networks, especially LSTM and NARX variants, outperformed traditional econometric methods for realized-volatility forecasting, while deep quantile estimation has shown material gains for VaR forecasting over linear alternatives. In practical terms, a volatility model answers “how big can the move be?” and a quantile model answers “how bad can this go?”—both are crucial inputs for sizing and gating. citeturn7view3turn17view0

For **regime adaptation**, I would favor either a regime-conditioned meta-model or a lightweight mixture-of-experts setup over a single universal forecaster. Recent factor-timing work shows value from multitask learning plus LSTM state extraction, and more recent regime-adaptive papers propose conditioning predictions on recent feature-return relationships or using regime-aware expert networks. Some of this regime work is recent and not yet consensus, but the broad point is solid: in finance, a static mapping from features to returns is often too brittle. citeturn7view5turn10search23turn7view12

For **trade filtering**, the right tool is a secondary classifier or meta-label model. López de Prado’s summaries describe meta-labeling as a second model that does not relearn the trade side; it learns whether the primary model’s proposed trade should be taken at all. That is an especially good fit for your current stack because you already have rich state descriptors. Rather than making every indicator vote directly on direction, let primary models propose opportunities and let a secondary model decide whether the setup is worth betting. citeturn10search20turn10search5

For **portfolio aggregation and final sizing**, the strongest systems increasingly move beyond raw directional voting and optimize for an economic target. Deep momentum research optimized signals with risk-adjusted objectives, while implementable-frontier research and related end-to-end portfolio studies show that including transaction costs in the learning objective can produce better net results than forecasting first and optimizing later. citeturn7view6turn7view1turn4search0

I would treat **reinforcement learning** as a later-stage tool, not the first thing to add. Even the FinRL-Meta benchmark paper describes finance as a particularly difficult playground for deep RL because of low signal-to-noise, survivorship bias, and backtest overfitting. RL can make sense after you already have a reliable supervised stack and a robust market simulator, but it is rarely the shortest path to a trustworthy first edge. citeturn14view0

## How to combine the models into actual trades

The best way to combine models is not to make each indicator cast a direct buy/sell vote. A better design is a **hierarchical ensemble** in which different models produce different kinds of evidence, and the final policy acts on their joint, out-of-fold-calibrated output. Stacking is the standard formalism for this: base models are trained first, their out-of-fold predictions are collected, and a final estimator is trained on those predictions to learn the combination rule. That is much better than hand-averaging when different models have strengths in different regions of state space. citeturn13view0turn13view1

For your stack, I would recommend five layers. The first is the **state layer**, which you mostly already have: your trend, volatility, prior-structure, participation, cross-timeframe, and regime descriptors. The second is the **opportunity layer**, where separate long-side and short-side models predict things like expected net return, probability of barrier hit, and rank score among all current candidates. The third is the **risk layer**, where separate models forecast realized volatility, downside quantile, and expected adverse excursion. The fourth is the **implementability layer**, where models forecast spread, slippage, and participation-rate cost. The fifth is the **decision layer**, a meta-model that determines whether the net expected utility is high enough to trade after all adjustments. This division is strongly aligned with what recent finance papers show works: economic objectives, regime dependence, ranking-based selection, and explicit handling of frictions. citeturn7view1turn18view0turn15view0turn7view5

A practical final trade score for each candidate setup could look like this:

\[
\text{NetEdge}_i
=
\hat p_i^{\text{win}} \cdot \hat \mu_i^{+}
-
(1-\hat p_i^{\text{win}})\cdot \hat \mu_i^{-}
-
\hat c_i
-
\lambda \hat q_i
-
\gamma \hat u_i
\]

where \(\hat p_i^{\text{win}}\) is a calibrated win probability, \(\hat \mu_i^{+}\) and \(\hat \mu_i^{-}\) are expected favorable and adverse moves, \(\hat c_i\) is expected trading cost, \(\hat q_i\) is a tail-risk estimate such as VaR or expected adverse excursion, and \(\hat u_i\) is an uncertainty or model-disagreement penalty. Trade only when \(\text{NetEdge}_i\) exceeds a threshold large enough to survive costs and model error. This formula is an inference from the evidence above, but it directly reflects what the literature keeps showing: prediction quality alone is not enough; net, risk-adjusted, cost-aware utility is what matters. citeturn17view0turn13view3turn7view11turn7view1

In your specific case, I would not combine models by equal weighting. I would use **regime-conditioned stacking**. In calm, trend-friendly states, put more weight on your trend and structure opportunity models. In volatile transition states, increase the weight on risk, participation, and abstention models. In conflicting cross-timeframe states, down-weight continuation signals and require stronger net edge. This is exactly the sort of adaptive combination suggested by recent regime-aware and meta-learning work, and it is more realistic than assuming one static blend should work in all environments. citeturn10search23turn7view12turn7view5

The one layer I would absolutely add is a **meta-label gate**. Let your primary models propose “candidate longs” and “candidate shorts.” Then train a secondary classifier on the out-of-fold history of those candidate trades to answer: “Was this trade worth taking after costs?” That secondary model should ingest the primary scores, regime indicators, vol state, participation, spread proxies, event flags, and model-disagreement measures. This is one of the cleanest ways to turn your current analytical stack into a trading stack without forcing every module to be directional. citeturn10search20turn10search5turn7view9

## How to know whether the ensemble is actually profitable

The first rule is that the combination itself must be validated **chronologically and leakage-safely**. If you use stacking, the meta-model must be trained on **out-of-fold predictions**, not on in-sample base-model outputs. That is true in general ML, and in finance it is even more important because leakage can make ensemble combinations look far better than they truly are. citeturn13view0turn13view1

The second rule is to use **purged validation with embargo**, and preferably also compare results against stronger robustness checks such as combinatorial purged cross-validation. López de Prado’s purged-CV summary highlights that overlaps around the test set must be removed to prevent leakage, and recent synthetic evidence argues that CPCV can reduce backtest overfitting more effectively than simpler methods in some financial settings. I would treat CPCV as an additional robustness layer rather than unquestioned doctrine, but purging and embargo should be non-negotiable. citeturn9search2turn9search4

The third rule is that every decision threshold must be selected on **net** performance, not statistical accuracy. The BTC walk-forward paper is a good reminder that naive sign rules can fail after costs even when forecasts contain some genuine predictive information. Likewise, trading-volume research shows that standard statistical objectives can be poor proxies for economic error; the downstream trading objective matters. So when tuning your ensemble, use selection criteria such as net Sharpe, drawdown-adjusted return, top-\(k\) precision after costs, and turnover-adjusted utility—not plain ROC-AUC or sign accuracy by itself. citeturn7view11turn18view0

The fourth rule is to protect yourself against research false positives. The Deflated Sharpe Ratio was designed specifically to correct for selection bias under multiple testing and non-normal returns. If you are going to search over many model families, thresholds, horizons, and blending rules, you need a metric like DSR or a similar multiplicity-aware check; otherwise you are very likely to select a lucky backtest. citeturn7view10

## A concrete blueprint for your next version

If I were extending your system, I would keep your current indicators as the **feature backbone** and add only a few highly leveraged model blocks.

First, add a **long-side opportunity model** and a **short-side opportunity model**, likely with boosted trees as the starting point, trained on your current state features plus newer implementability inputs. Their job should be to estimate either expected net return or barrier-hit probability over a fixed horizon. This is the first place where your rich state engine becomes a genuine opportunity engine. Trees are the pragmatic first choice here because your features are tabular, heterogeneous, and likely full of nonlinear interactions. citeturn7view0turn13view2

Second, add a **ranking model** if you have multiple simultaneous candidates. Use a CatBoost ranker or another learning-to-rank model to rank symbols or setups within each decision batch. This is especially attractive if you often see several plausible trades at once and only want to take the best few. citeturn15view0turn13view4

Third, add a **risk model** that predicts realized volatility and a downside quantile or expected adverse excursion. If you already have EWMA volatility, do not replace it—use it as a benchmark and feature. The new model should answer a different question: not “what is the current risk regime?” but “how much could this specific setup hurt over the trade horizon?” citeturn7view3turn17view0

Fourth, add an **implementability model**. At minimum, estimate expected spread/slippage using participation rate, relative volume, session phase, recent range, bar-to-bar gap behavior, and any available liquidity proxy. If you can get better data, include actual spread and depth. This is probably the single most practical addition you are missing. citeturn18view0turn7view1

Fifth, add a **meta-label gate** trained only on candidate trades proposed by the primary models. The label should be whether the trade was economically worthwhile after costs, not whether price moved in the forecasted direction. That gate should consume the primary scores, risk forecasts, implementability forecasts, regime features, and model disagreement. citeturn10search20turn10search5turn13view3

Sixth, add a **portfolio layer** that turns candidate trades into constrained exposures. This layer should cap correlated bets, volatility-target the book, and zero out trades whose edge is positive only under optimistic cost assumptions. Modern research on implementable efficient frontiers strongly supports tying learning and allocation to realistic frictions rather than optimizing on gross forecasts and hoping portfolio construction fixes the rest. citeturn7view1turn4search10

If you want the shortest path to a stronger system, I would aim for this operating design: your current indicator stack becomes the feature engine; boosted-tree long and short models produce candidate edges; a ranker orders candidates; a volatility and tail-risk model sets risk-adjusted sizing; a cost model estimates whether the edge survives execution; and a meta-label gate decides whether to trade at all. That is a much stronger architecture than either a single predictor or a naive majority vote. It also matches the broader lesson from the research: profitable ML trading is usually not about one magical model, but about **a disciplined ensemble of specialized models with a cost-aware, uncertainty-aware final decision rule**. citeturn13view0turn7view1turn15view0turn17view0turn10search23

The last point is the most important: no model stack guarantees profit. Financial data are noisy, non-stationary, and frequently driven by jumps that are only partly explained by observable public information. The realistic goal is not certainty; it is to build a system that finds a small edge, abstains often, survives frictions, and remains stable across genuinely unseen periods. That is what the best machine-learning trading strategies are actually trying to do. citeturn7view12turn7view2turn14view0

Yes. The previous research **mentioned the idea**, specifically:

* predicting whether take-profit is reached before stop-loss;
* predicting expected adverse excursion;
* using barrier-hit probability as an opportunity-model target.

However, it did **not fully separate entry-price selection from execution probability**. These are related but different problems.

# 1. Do not predict one “correct fill price”

A better formulation is:

> For several possible entry prices, estimate the probability of being filled and the expected outcome after being filled.

For a candidate long entry (e), define:

* (SL(e)): stop-loss associated with that entry;
* (TP(e)): take-profit associated with that entry;
* (H_e): maximum time allowed for entry;
* (H_t): maximum holding time after entry.

You want to estimate:

[
P(\text{fill at } e \text{ before } H_e)
]

and, conditional on the fill:

[
P(TP(e)\text{ before }SL(e)\mid \text{filled at }e)
]

This is preferable to directly predicting:

```text
The ideal entry will be $102.37
```

A single-point estimate hides uncertainty and may be economically useless if the market never reaches it.

Instead, score a grid of possible entries:

```text
market entry
-0.25 volatility units
-0.50 volatility units
-0.75 volatility units
-1.00 volatility units
prior support level
prior breakout-retest level
```

Then choose the candidate with the best expected utility.

---

# 2. This can reduce a specific type of false positive

Suppose your directional model correctly predicts that price will eventually increase.

The path might nevertheless be:

```text
Signal price: 100
Price falls:   96
Stop-loss:     97
Price rises:  108
Take-profit:  106
```

The directional forecast was correct, but the trade lost because the entry was poor relative to the path.

An entry model could conclude:

```text
Long direction is attractive.
Immediate entry has excessive adverse-excursion risk.
Wait for an entry around 97–98.
```

This reduces **path-related false positives**:

* correct final direction;
* incorrect entry timing;
* stop reached before the forecasted movement develops.

It does not necessarily fix genuinely incorrect directional forecasts.

A useful decomposition is:

[
\text{Trade failure}
====================

\text{wrong direction}
+
\text{bad entry}
+
\text{bad SL/TP geometry}
+
\text{execution failure}
]

Different models should address each component.

---

# 3. Academic support for the approach

## Optimal entry with stop-loss constraints

Leung and Li formulate entry and exit as an optimal double-stopping problem with transaction costs and a stop-loss. Their model derives an **optimal entry interval**, rather than assuming the trader should enter immediately. A particularly relevant result is that entering too close to the stop-loss can be suboptimal because the probability of being stopped becomes too high. ([arXiv][1])

This directly supports your intuition:

> The existence of a directional opportunity does not imply that every entry price is acceptable.

However, their analytical result assumes a mean-reverting Ornstein–Uhlenbeck process. It is theoretically useful but cannot be assumed to generalize automatically to arbitrary stock trends, crypto or breakout strategies.

Baviera and Santagostino Baldi similarly derive optimal entry and exit levels using probabilities of reaching specified levels, expected first-passage times and expected first-exit times. Their strategy explicitly connects stop-loss selection with entry-price selection. ([arXiv][2])

These papers represent the classical mathematical version of what you are proposing. Your ML model would replace the rigid stochastic-process assumptions with a learned conditional distribution.

## Predicting whether a limit order will fill

Arroyo, Cartea, Moreno-Pino and Zohren model limit-order fill time using survival analysis. Their model maps time-varying limit-order-book information to a distribution of fill times at different book levels. This supports predicting a **fill probability distribution**, rather than one exact fill price. ([arXiv][3])

Fabre and Ragel go one step closer to your intended system. They train a model for fill probability and use it to decide:

* whether to execute immediately or post a limit order;
* how far from the current market to place the order;
* how to account for the cost of not being filled.

Their framework explicitly characterizes an optimal placement distance over a fixed execution horizon. ([arXiv][4])

## The adverse-selection problem

A better entry price is not automatically a better trade.

For a long trade, a lower buy limit becomes more likely to fill precisely when the market is moving downward. That can mean the limit order is filled under deteriorating conditions.

Lehalle and Mounjid emphasize this adverse-selection effect: limit-order fill probability is related to liquidity imbalance, and a high probability of receiving a fill can coincide with a high probability of the price continuing against the trader. They also show that latency limits the ability to cancel and reposition orders when conditions change. ([arXiv][5])

Therefore, your model must not optimize:

[
\max_e P(\text{fill at }e)
]

It should optimize:

[
\max_e P(\text{fill})\times
E[\text{net utility}\mid\text{fill}]
]

A fill is not inherently successful.

---

# 4. The correct decision function

For every candidate entry (e), calculate something resembling:

[
\begin{aligned}
U(e)
=&;
P_{\text{fill}}(e)
\Big[
P_{\text{TP-first}}(e)\cdot G(e)\
&-
P_{\text{SL-first}}(e)\cdot L(e)
--------------------------------

## C_{\text{execution}}(e)

C_{\text{adverse selection}}(e)
\Big]\
&-
\left(1-P_{\text{fill}}(e)\right)
C_{\text{missed opportunity}}(e)
\end{aligned}
]

Where:

* (G(e)) is the net profit if TP occurs first;
* (L(e)) is the net loss if SL occurs first;
* (C_{\text{execution}}) includes spread, fees and slippage;
* (C_{\text{adverse selection}}) penalizes fills associated with deteriorating market state;
* (C_{\text{missed opportunity}}) measures the cost of waiting while the expected movement occurs without a fill.

The chosen entry is:

[
e^*=\arg\max_e U(e)
]

The final rule is:

[
\text{Trade only if }
U(e^*)>\tau
]

Otherwise:

```text
Do not trade.
```

Importantly, the possible actions should include:

```text
market order now
passive limit order
wait and reassess
cancel signal
```

---

# 5. Recommended model architecture

## Model 1: Direction or opportunity model

Its job is:

```text
Is there a sufficiently strong long or short opportunity?
```

Suitable models:

* CatBoost classifier or regressor;
* CatBoostRanker when comparing multiple opportunities;
* Elastic Net as a stable baseline;
* temporal CNN when genuine sequential information exists.

Output examples:

[
\hat r,\quad P(up),\quad P(down),\quad rank
]

Your current trend, regime, volatility, structure and participation features belong primarily here.

## Model 2: Entry-path model

Its job is:

```text
For this signal and candidate entry, what happens after entry?
```

Use a three-class target:

[
y(e)\in
{
TP\ first,;
SL\ first,;
neither
}
]

A CatBoost multiclass model would be a strong first implementation.

Inputs should include:

* candidate-entry offset;
* distance to prior high and low;
* stop distance;
* take-profit distance;
* current and predicted volatility;
* trend quality;
* CUSUM state;
* cross-timeframe agreement;
* participation;
* regime;
* time since the original signal;
* movement between signal generation and potential entry.

Represent candidate entry distance in volatility units:

[
z_e =
\frac{e-P_t}{\hat\sigma_t}
]

Do not use raw dollar distance because it is not comparable across assets or volatility regimes.

## Model 3: MFE and MAE models

Predict:

* maximum favourable excursion;
* maximum adverse excursion.

Prefer quantile regression:

[
Q_{0.1}(MAE),\quad
Q_{0.5}(MAE),\quad
Q_{0.9}(MAE)
]

This can answer:

```text
How deeply is the trade likely to move against me before succeeding?
```

It is often more useful than predicting only the final return.

For example:

```text
Expected final return:        +2.0%
Median adverse excursion:     -0.7%
90th-percentile adverse move: -2.4%
```

A 1% stop may therefore be incompatible with the trade’s normal path despite positive expected return.

## Model 4: Fill-time model

With order-book or tick data, predict:

[
P(T_{\text{fill}}\leq h\mid X_t,e)
]

A survival-analysis model is especially suitable because unfilled orders are censored observations rather than ordinary negative examples. The limit-order-book research above uses exactly this framing. ([arXiv][3])

Start with:

* Cox proportional hazards;
* gradient-boosted survival trees;
* CatBoost-based time-bin classification.

Only move to convolutional Transformers when you have enough high-quality L2 order-book data.

## Model 5: Final meta-gate

The final model receives:

```text
direction score
rank score
candidate entry
TP-first probability
SL-first probability
fill probability
predicted MFE
predicted MAE
execution cost
model disagreement
regime
```

It predicts:

[
P(\text{positive net trade}\mid \text{all model outputs})
]

This is the final false-positive filter.

---

# 6. A suitable target structure

For each original signal at time (t), generate several candidate entries:

```text
candidate 0: immediate market entry
candidate 1: -0.25σ pullback
candidate 2: -0.50σ pullback
candidate 3: -0.75σ pullback
candidate 4: prior structural support
```

For each candidate record:

```text
was entry touched?
was it realistically filled?
time to fill
state at fill
TP before SL?
SL before TP?
neither before expiry?
time to outcome
maximum adverse excursion
maximum favourable excursion
net PnL
```

The dataset becomes approximately:

```text
signal_id | candidate_entry | candidate_features | outcome
```

All candidate rows belonging to one signal must remain in the same fold. Otherwise, one entry candidate could enter training while another candidate from the same future price path enters validation.

---

# 7. Critical limitation of OHLCV data

With ordinary candles, you can model whether a price level was **touched**, but not reliably whether a real limit order was filled.

For example, a candle low below your buy limit does not tell you:

* what the ask price was;
* whether enough volume traded at that level;
* your queue position;
* whether your order would have been partially filled;
* whether the market touched the price for one transaction only.

There is another serious issue:

```text
High reaches TP
Low reaches SL
during the same candle
```

OHLC does not reveal which occurred first.

For such bars you must either:

* use lower-frequency or tick data to recover the sequence;
* label them ambiguous and remove them;
* assume the adverse outcome occurred first;
* model both possible outcomes as a sensitivity test.

Assuming TP occurred first will substantially inflate the backtest.

For a genuine entry-execution model, you ideally need:

```text
bid and ask
trades
tick timestamps
order-book depth
queue information or proxies
```

With OHLCV alone, describe the output as a **candidate entry touch model**, not a true fill model.

---

# 8. How to test whether it actually helps

Compare these policies using identical signals:

```text
A: immediate market entry
B: fixed pullback entry
C: structure-based entry
D: ML-selected entry
E: ML-selected entry plus meta-gate
```

Evaluate:

* net expectancy per original signal;
* expectancy per filled trade;
* TP-before-SL rate;
* fill rate;
* missed profitable signals;
* average adverse excursion;
* time to fill;
* execution costs;
* maximum drawdown;
* Sharpe and Sortino;
* results by regime.

A dangerous result would be:

```text
Win rate increased from 50% to 65%
but only 20% of signals were filled
and most large winners were missed.
```

The entry model must improve **total net utility**, not merely the win rate of the surviving trades.

# Recommended first implementation

Given your current feature set, I would start with:

```text
1. Primary CatBoostRanker
   → ranks long and short candidates

2. CatBoost multiclass entry-path model
   → TP first / SL first / neither

3. CatBoost quantile regressors
   → MFE and MAE quantiles

4. Candidate-entry optimizer
   → selects immediate entry or volatility-scaled pullback

5. Meta-classifier
   → trade / no trade

6. Later: survival fill model
   → only after obtaining tick or order-book data
```

So your proposed approach is academically defensible and potentially valuable. The important refinement is that you should not merely predict a lower entry price. You should jointly model:

[
\boxed{
\text{fill probability}
\times
\text{post-fill barrier outcome}
\times
\text{net payoff}
}
]

That is the correct connection between **alpha prediction, entry timing, stop-loss survival and execution quality**.

[1]: https://arxiv.org/abs/1411.5062 "Optimal Mean Reversion Trading with Transaction Costs and Stop-Loss Exit"
[2]: https://arxiv.org/abs/1706.07021 "[1706.07021] Stop-loss and Leverage in optimal Statistical Arbitrage with an application to Energy market"
[3]: https://arxiv.org/abs/2306.05479 "[2306.05479] Deep Attentive Survival Analysis in Limit Order Books: Estimating Fill Probabilities with Convolutional-Transformers"
[4]: https://arxiv.org/abs/2307.04863 "[2307.04863] Interpretable ML for High-Frequency Execution"
[5]: https://arxiv.org/abs/1610.00261 "[1610.00261] Limit Order Strategic Placement with Adverse Selection Risk and the Role of Latency"
