# Executive Summary

Walk-forward validation for time-series trading models must be redesigned to systematically explore all robust CV schemes, avoid data leakage, and align model evaluation with trading objectives.  Instead of a single fixed holdout, we recommend **multiple schemes** (rolling vs. expanding, nested vs. anchored, purged CV, etc.) and explicit *embargo buffers* to eliminate look-ahead bias.  Window lengths should be chosen based on domain factors (seasonality, target horizon) and tested as hyperparameters.  Train/val/test splits must account for the forecast horizon and avoid overlapping label periods (use “purging” and an embargo gap).  Feature and hyperparameter tuning should be wrapped in **nested** time-series CV loops to prevent leakage.  Evaluation should prioritize trading-centric metrics (e.g. profit after costs, Sharpe, drawdown) alongside statistical metrics (AUC, RMSE, Spearman, precision@k).  For *feature selection*, use time-safe methods (e.g. CatBoost’s `select_features` with SHAP) and assess feature stability across folds.  For *hyperparameters*, use sequential halving or Bayesian search inside each fold’s inner loop.  We outline these recommendations below, with a structured table of validation strategies, pros/cons, and recommended defaults, plus a step-by-step pipeline diagram (Mermaid flowchart) and pseudocode snippets.

## 1. Walk-Forward & Cross-Validation Strategies

**Time-series data must preserve temporal order**. Standard k-fold CV (random shuffling) is invalid, as it leaks future information.  Two basic “walk-forward” families dominate (see Table 1):

- **Rolling (Fixed-Window) Walk-Forward:** Each fold trains on a fixed-size window of past data and tests on the immediately following period.  The window *slides* forward by a fixed step (often 1 period) each iteration.  This “rolling window” adapts to regime changes (by forgetting old data) but introduces higher variance and requires tuning the window length **W**.  Use rolling CV when you suspect non-stationarity (shifts in regime or seasonality).  Important: choose **W** so as to cover at least one full seasonal cycle or match the expected retraining period.  For example, one might try W equal to 1–2 years of daily data when seasonality exists.

- **Expanding (Growing-Window) Walk-Forward:** Starts with an initial training period (size *m*) and at each fold grows the training set to include all data up to the current point.  No data is ever discarded.  Early folds have small training sets, later ones use all history.  Expanding CV yields more stable error estimates (lower variance) since it maximizes data usage.  It assumes older data remains informative (i.e. stationarity) and may *dilute* recent changes with outdated data.  Use expanding windows for shorter series or when stationarity is plausible.  A common heuristic: if in doubt start with expanding (no need to choose W) and then test fixed W to see if results improve.

- **Anchored (Backtest) Split:** A special case of expanding where you fix a long initial training set and then reserve a contiguous *final* period for testing (i.e. one train/test split).  This mimics a single historical backtest, but as found in [12] its main drawback is that it is only *one path* (hence high variance and risk of overfitting to that period).  It is equivalent to the first iteration of an expanding-windows CV.  Unlike CV, anchored testing has a clear historical interpretation (simulating a paper-trading scenario).

- **Purged K-Fold CV (TimeSeriesSplit with gaps):**  Adapt standard K-Fold by **purging** training rows that overlap the label horizon of each test fold, and optionally **embargoing** a buffer after each test block.  López de Prado’s PurgedKFold ensures no look-ahead leakage by dropping any train sample whose timestamp falls within the label window of the test set.  An additional “embargo” removes a short period after each test block to prevent contamination from spillover effects.  PurgedKFold CV is generally more stable than naive WF because it produces multiple OOS scenarios, covering different time regions.  In practice one splits the data into contiguous blocks and uses something like scikit-learn’s `TimeSeriesSplit(gap=embargo, ...)`, or custom code to drop/skip overlapping periods.  *Recommended:* use PurgedKFold with an embargo = (target horizon length), as López de Prado advises.  This prevents label overlap and is less optimistic than a simple anchored test.  For example, with daily data and a 5-day forecast horizon, one might drop 5 days from training on each side of the test period.

- **Nested Cross-Validation:**  To tune hyperparameters in a time-series-friendly way, a **nested CV** is advisable.  This means each outer “fold” is a time-based train/test split (e.g. one cycle of walk-forward), and within that fold you perform an inner time-series CV (e.g. another rolling/expanding sequence on the training portion) to select hyperparameters.  Nested CV prevents leakage from validation into training: without it, hyperparameters would be tuned on the same data used for final evaluation, leading to over-optimism.  The outer loop estimates generalization error across multiple periods, while the inner loop optimizes the model.  (Nested CV is expensive but can be limited to a few folds or replaced with careful hold-out on the last window if compute is tight.)

- **Combinatorial Purged CV (CPCV):**  This advanced method (LdP 2018) enumerates all combinations of train/test blocks (with purging) to simulate every possible backtesting “path”.  It is extremely robust: a recent study found that CPCV yielded much lower probability of backtest overfitting and higher deflated Sharpe ratios than any single WF or KFold.  In practice, CPCV is very costly (combinatorial explosion), but conceptually it shows the benefit of using many different out-of-sample scenarios instead of one.  If feasible, one might implement a simplified CPCV by choosing a few different partitionings (e.g. test sets from each quarter/year) and averaging results.

**Table 1.** *Comparison of time-series validation strategies.*
| Strategy                  | Key Idea                                                  | Pros                                                  | Cons                                                    |
|---------------------------|-----------------------------------------------------------|-------------------------------------------------------|---------------------------------------------------------|
| **Rolling Window (fixed)**| Slide a fixed window of past data forward in time.        | Adapts to regime shifts; mirrors fixed-memory models. | Must choose window size *W*; higher variance; requires retraining often. |
| **Expanding Window**      | Start from origin; grow training set each fold.           | Uses all data (stable errors); no W to tune.          | Assumes stationarity; early folds noisy (small sample); older data may dilute new regimes. |
| **Anchored Split**        | One long train → one test period (last segment).          | Clear historical backtest; simple.                    | Single scenario (high variance); not generalizable.                     |
| **Purged K-Fold CV**      | K-fold with time-order; remove overlaps & embargo.        | Multiple OOS paths; prevents label leakage. | More complex splitting; test folds still contiguous blocks; fewer samples per fold.   |
| **CPCV (Purged)**         | All combinations of k-out-of-n blocks with purging.       | Extremely robust; low backtest overfit.     | Combinatorial complexity (not scalable); heavy compute. |
| **TimeSeriesSplit** (sklearn) | A form of expanding CV (each train is superset).     | Built-in support (e.g. `gap` parameter). | Each test is one sample or block; sequential only.     |

*(Cells cite key features from references.)*

## 2. Window-Size & Split Planning

**Heuristics for Window Length:**  The choice of train/validation window lengths depends on the data frequency and target horizon:
- **Seasonality:** Ensure the training window covers at least one or two full seasonal cycles of the data.  For monthly data, use ≥24 months; for daily, several years if annual seasonality exists.
- **Forecast Horizon:** The out-of-sample window (test period) should match the business need (e.g. 1-day, 1-week ahead) and at least equal one forecast horizon. For rolling CV with horizon *h*, you might step by *h* each fold, or use overlapping tests to get more samples.
- **Computational Budget:** Longer windows and many folds yield better stability but cost more compute.  We recommend trying a grid of plausible window sizes (e.g. {60, 90, 180, 360} days for 1-day-ahead models) and measuring performance/stability.  Treat window length as a hyperparameter.

**Train/Val/Test Splits:** A typical walk-forward cycle might allocate ~50–80% of data to training and the next 10–20% to validation, reserving the final 10–20% for a held-out test (or using cross-validation instead of a fixed test).  If data is plentiful, shorter windows can be used to increase the number of folds.  **Overlap vs. Non-Overlap:**  You can allow overlap between consecutive test folds (sliding by one period) to maximize data usage, or use non-overlapping “blocks” (e.g. one quarter of data each).  Non-overlapping tests avoid correlated returns between folds but reduce sample size.  In practice, use overlap but always **purge**/embargo to avoid leakage (see below).

## 3. Leakage Control: Purging & Embargo

A critical step is to **avoid look-ahead bias**.  In forecasting targets that depend on future data (e.g. “price goes up over next 5 days”), training data can inadvertently include information from a label period.  Two remedies are:

- **Purging Overlap:** Remove any training observations whose timestamp falls within the label formation window of the test set.  For example, if a label covers days *t+1…t+5*, drop any training samples from *t+1…t+5* (even if they occurred before the test block).  This ensures the model can’t “peek” at the future through correlated features.

- **Embargo/Gaps:** Additionally, impose a gap (e.g. 5% of the data length or equal to the longest label horizon) **after** each test period during which you also exclude data from training.  This accounts for the fact that markets react with a lag: even if a training point is outside the label window, it might still be influenced by events in the test period.  For example, with daily data and a 2-day label, you might embargo the 2 days after each test split (or a fixed percentage).

These practices are formalized in PurgedKFold CV.  Always assume that labels are not IID: apply these leakage guards whenever training/validation windows border each other.

## 4. Evaluation Metrics for Trading

Choosing the right metrics is crucial. Standard ML metrics (AUC, RMSE, logloss) are still useful for monitoring statistical fit, but **business metrics** tied to trading performance must guide model selection.  Key categories:

- **Statistical Metrics:** Use AUC or accuracy for classification signals, RMSE/MAPE for regression.  Consider rank-based measures (Spearman’s ρ, Kendall tau) if your aim is to get the ordering of assets right.

- **Profit Metrics:** Simulate a simple strategy to compute **net profit after costs** (fees/slippage), **Profit Factor** (gross wins / gross losses), **Sharpe Ratio**, and **Max Drawdown**.  López de Prado and practitioners emphasize evaluating **precision@K** (accuracy among the top K% signals) and **turnover-adjusted Sharpe** rather than raw accuracy.  For example, compute the PnL of the top decile of predicted long signals minus short signals.  A model with modest AUC can still be valuable if its top recommendations reliably produce profit.

- **Composite View:** Use multiple metrics to avoid “fishing” for one.  For ranking models, track metrics like **Normalized Discounted Cumulative Gain (NDCG)** or **Average Precision** if applicable.  For risk, monitor the distribution of monthly returns (Sharpe, Sortino, MDD).

In model selection, one might optimize an in-sample proxy (e.g. logloss or RMSE) under CV, but always **validate** that the chosen model also performs well in PnL metrics on unseen data.  For example, tune hyperparameters by CV minimizing RMSE, then check that the resulting model yields a positive Sharpe on out-of-sample folds.

## 5. Feature Selection Workflow

Feature selection should also be time-aware and cross-validated: avoid selecting features on the full dataset before CV. Suggested procedure:

1. **Filter Obvious Features:** Remove constant or near-constant features; eliminate features with data leakage risk (e.g. look-ahead volumes). Group related features (e.g. price, momentum, volatility signals) to preserve interpretability.

2. **Univariate Ranking:** (Optional) Quickly rank features by correlation with the target or by simple feature importance on a baseline model, strictly within the train portion. For example, train a small tree on each fold’s train set and rank features by gain. This identifies families of useful features.

3. **Cross-Validated Importance:** Use model-based methods (e.g. CatBoost’s built-in feature importance or SHAP) computed on each train split.  Note variability of importance across folds – features that are only transiently important may indicate overfitting.

4. **Select_Features (CatBoost):** CatBoost provides a `select_features` method that performs recursive feature elimination with SHAP or loss-change criteria.  For example:
```python
# Pseudocode for CatBoost select_features
model = CatBoostRegressor(iterations=500, random_seed=0)
summary = model.select_features(
    Pool(train_X, train_y),
    eval_set=Pool(val_X, val_y),
    features_for_select='0-99',           # all features
    num_features_to_select=20,           # choose top 20
    steps=5,
    algorithm=EFeaturesSelectionAlgorithm.RecursiveByLossFunctionChange,
    shap_calc_type=EShapCalcType.Regular,
    train_final_model=False
)
selected = summary['selected_features_names']
```
This safely evaluates feature subsets on a hold-out set to drop *harmful* features. Use `algorithm=RecursiveByLossFunctionChange` (balanced speed/accuracy) or `RecursiveByShapValues` (most accurate).

5. **Permutation Importance:** As a final check, use permutation importance **within each validation fold** to see if shuffling a feature significantly drops CV score. This guards against over-reliance on a feature that might correlate spuriously.

6. **Stability Check:** Record how often each feature is selected or ranked in the top set across folds. Features appearing consistently are more reliable. If different folds pick completely different features, the model may not generalize.

*Budget:* Feature selection (especially SHAP) is expensive. A practical approach is to select features once on a representative fold or on a hold-out validation set, rather than rerunning it in every iteration.  Alternatively, do a quick selection on the first (or largest) window and reuse the same mask for subsequent windows to save time.

## 6. Hyperparameter Tuning Workflow

Hyperparameter tuning for time-series models should respect temporal structure:

- **Parameter Types:** In CatBoost and other tree-based models, important hyperparameters include tree depth, learning rate, L2 regularization, `border_count` (number of bins for numerical features) and `feature_border_type` (quantization strategy).  By default, CatBoost uses up to 254 splits (bins) on CPU and 128 on GPU; increasing `border_count` (e.g. to 254) can improve quality at the cost of time.

- **Nested CV or Hold-Out:** As noted, perform hyperparam search *inside* a time-series CV loop to avoid bias.  For example, an outer rolling or expanding loop generates folds; within each training segment, run a grid/random/Optuna search, using a smaller internal CV or a validation split.  One can also use *sliding* inner folds.

- **Search Strategy:**
  - *Grid/Random Search:* Start with a coarse grid (e.g. depth∈{4,6,8}, learning_rate∈{0.01,0.03,0.1}, etc) if compute allows.
  - *Bayesian Optimization:* Tools like Optuna can more efficiently explore large spaces by learning from past trials.
  - *Successive Halving:* Use `HalvingGridSearchCV` or CatBoost’s own `randomized_search` to drop poor candidates early. This is useful when model training is slow.

- **Ordered Tuning:** It often makes sense to tune coarse- to fine. For example:
  1. Fix window and features; tune depth and learning rate together.
  2. With best depth/lr, fine-tune regularization parameters (L2 leaf).
  3. Finally, experiment with `border_count` and `feature_border_type`. CatBoost supports `--border_count` per feature via `per_float_feature_quantization`; try the default 254, and also a smaller (for speed) or larger (for finer splits) to see impact.

- **Compute Cost:** Nested search across many folds is expensive. Limit the number of outer folds (e.g. 3–5 walk-forward steps) for tuning, then validate with all folds using the chosen hyperparams. Alternatively, use an expanding-window outer loop and stop after a few steps.

## 7. Model Families & WF Differences

Different model types interact with walk-forward validation as follows:

- **Tree Ensembles (CatBoost, XGBoost, LightGBM):** These are our baseline.  They treat each sample independently, so any CV approach above applies directly.  For CatBoost specifically, use `has_time=True` (or ordered Pool with a time column) to ensure data is not randomly permuted internally.  CatBoost’s handling of categorical features and default symmetric trees often yields robust, interpretable models.

- **Temporal Models (ARIMA, ETS, Prophet, etc.):** Traditional forecasting models assume a single time series (not panel) and typically use expanding-window hold-out (e.g. train until time T, forecast T+1…).  Their “CV” is usually based on time-series cross-validation (rolling windows) too.  If using these, the same fold definitions apply, but feature selection is less relevant since features are usually lags of the target.

- **Stateful Deep Models (RNNs, LSTMs, Transformers):** These consume sequences.  In practice, you would still define train/test splits by time, then feed sliding windows of past *n* steps into the network.  Ensure that hidden states are reset between folds (no leakage of memory).  Deep models often require fixed-size sequences, so one might use rolling windows of fixed length as “samples” and train/validate on those.  Hyperparameter tuning for deep nets (learning rate, dropout, etc.) should still use time-based CV.  Note: Deep models are typically more data-hungry and slower to train; cross-validation with them is costly.

- **Online or Incremental Models:** Algorithms like online SGD or streaming tree ensembles (e.g. River library) update with each new point.  These can naturally use walk-forward by training on each new sample or batch and evaluating on the next.  Walk-forward validation for online learning can simply simulate a live run: train up to t, predict t+1, then include t+1 in training, etc.

- **Ensembles & Stacking:** You might ensemble diverse models (e.g. averaging catboost + neural net predictions).  Walk-forward remains the same, but ensure that stacking or blending does not leak data (do inner CV stacking within each fold).

In all cases, **the validation design (e.g. rolling vs expanding)** is independent of the model family.  However, tree ensembles benefit from features like CatBoost’s quantization and ordered boosting (as above).  Models that accept a time index (e.g. setting `has_time=True` in CatBoost, or passing a `timestamp` to other libraries) should use it for reproducibility.

## 8. Experimental Plan & Diagnostics

To systematically upgrade the walk-forward pipeline, run a suite of experiments and analyses. For each experiment, record not just average performance but stability (variance) across folds:

- **Validation Grid:** Create a grid over key validation design choices:
  - **Window Size:** Try several train window lengths (e.g. 90d, 180d, 360d, 720d) and step sizes (e.g. 1-day rolls vs. block shifts).
  - **Fold Type:** Test rolling vs expanding.
  - **Embargo Length:** Vary the embargo (e.g. 0%, 1%, 5% of data) or use the label horizon.
  - **Test Overlap:** Compare overlapping versus non-overlapping test splits (sliding vs block).

- **CatBoost Parameters:** In each CV setting, also vary CatBoost quantization: `border_count` (64, 128, 254) and `feature_border_type` (Median, Uniform, GreedyLogSum, MinEntropy, etc).  *Border type tests:* uniform splits often speed training but median/quantile splits can capture distributions better.  Use CatBoost’s “save_borders” or `get_borders()` to inspect how splits change.

- **Feature Set Variations:** Start with the full feature set, then repeat with pruned sets (top 50, 100, 200 by importance).  Also test groupwise exclusion (e.g. drop all volume-related features, then all volatility features) to see which families matter.

- **Hyperparameter Search:** For each combination above, run a tuning routine (grid or Bayesian) within each training fold. For example, a small randomized search (20–50 trials) for learning_rate and depth.  Alternatively, use successive halving (e.g. via `HalvingGridSearchCV`) to focus on promising configs.  Record the best hyperparameters per fold and note their consistency.

- **Stability Metrics:** In addition to mean and std of evaluation scores across folds, compute:
  - *Fold Variance:* Variance of target metric (e.g. RMSE, Sharpe) across folds.
  - *Rank Stability:* Measure how correlated feature importance or coefficient rankings are between folds.  For example, Spearman correlation of top-20 features between fold A and B.
  - *Turnover:* The fraction of top-K predictions that change between successive folds.  High turnover implies unstable signals.

- **Diagnostics & Visualizations:** Produce the following charts for insight:
  - **Border Distributions:** Plot the chosen split values for numeric features (CatBoost’s borders) across experiments. Uniform splitting yields evenly spaced borders, while “Median” splits concentrate around quantiles.
  - **Feature Importance over Folds:** For top features, plot their relative importance score in each fold (e.g. bar chart per fold).  This highlights if a feature is consistently important.
  - **Prediction Rank vs Return:** Scatter or rank correlation plots of predicted signal strength versus actual forward return for each fold.  Ideally, stronger signals should correspond to higher returns.
  - **Cumulative PnL per Fold:** Simulate a simple strategy (e.g. long top decile, short bottom decile) on each fold’s test data and plot cumulative PnL curves.  This directly shows any drift or worse-than-random performance.

- **Comparison Table:**  Compile results in tables, e.g.:

  | CV Scheme         | Avg Metric (Sharpe) | Std (Sharpe) | Key Hyperparams              | Compute (mins) | Notes                      |
  |-------------------|---------------------|--------------|------------------------------|----------------|----------------------------|
  | Rolling W=180     | 1.2                 | 0.3          | depth=6, lr=0.03, borders=128 | 90             | High turnover, decent PnL  |
  | Expanding W=365   | 1.0                 | 0.2          | depth=4, lr=0.05, borders=254 | 75             | More stable, slightly lower Sharpe |
  | Purged KFold (5x)| 1.15                | 0.25         | depth=5, lr=0.01, borders=128 | 120            | Lower PBO, moderate Sharpe |
  | CPCV (subset)     | 1.3                 | 0.15         | N/A                          | 300 (est.)     | Very low overfit risk|

  Such tables (filling with your test results) make it easy to recommend a default strategy (e.g. “Expanding window of 1 year, 5-fold purged CV for tuning”) and to highlight trade-offs.

- **Recommended Defaults:** Based on initial tests, one might pick: e.g. **Expanding-window CV** on the final 2 years with a fixed 20% embargo, tune CatBoost with depth=6, lr=0.05, border_count=254 (default) and feature_border_type=GreedyLogSum (balance precision and variance).  These serve as a starting point; alternatives (e.g. rolling W=180) can be tried if performance is inadequate.

## 9. Pipeline Flowchart

For clarity, here is a simplified Mermaid flowchart of the recommended pipeline.  It illustrates the sequence: prepare data, define CV splits, perform feature selection and hyperopt within each fold, evaluate metrics, then aggregate results and finalize the model.  (In practice, steps like “Feature Engineering” and “Backtest” loop may repeat.)

```mermaid
flowchart LR
  A[Data Ingestion] --> B[Feature Engineering & Labeling]
  B --> C[Define Walk-Forward Splits]
  C --> D{For each fold}
  D --> E[Train Model (with hyperparam search)]
  E --> F[Validation / Test Predictions]
  F --> G[Collect Metrics & PnL]
  D --> H[Feature Selection Loop]
  H --> E
  G --> I{End of folds}
  I --> J[Aggregate Results & Stability Analysis]
  J --> K[Select Best Model & Params]
  K --> L[Final Model Training on All Data]
  L --> M[Deployment / Live Testing]
```

```mermaid
flowchart TD
    subgraph Walk-Forward Pipeline
      A[Load and preprocess data]
      B[Feature Engineering\n(encode, lag, aggregate)]
      C[Define CV splits\n(rolling/expanding + embargo)]
      D[Per-fold Training & Tuning]
      E[Evaluate on fold test set]
      F[Collect metrics\n(PnL, Sharpe, etc.)]
      G[Feature selection (CV loop)]
      H[Aggregate results]
      I[Analyze stability]
      J[Choose final model]
    end
    A --> B --> C --> D --> E --> F --> I --> J
    D --> G --> D
    J --> K[Train final model on full data]
    K --> L[Backtest on holdout]
```

Each box corresponds to one of the steps above.  In particular, steps D–G form a nested loop: **D** (train/tune) and **G** (feature selection) happen inside each fold of **C**.

## 10. Actionable Roadmap

1. **Catalog Current Setup:** Verify how your existing optimizer sets splits, window sizes, and labels. Determine if it already purges or embargoes.
2. **Implement Split Variants:** Code rolling and expanding window generators. Use scikit-learn’s `TimeSeriesSplit` with `gap` or write custom loops (see pseudocode below).
3. **Add Purge/Embargo:** Integrate label purging. For example, exclude any training indices that overlap the current test period’s label horizon.
4. **Set Up Metrics Logging:** Extend the pipeline to record chosen metrics (AUC/RMSE, plus PnL outcomes) on each fold. Plot these during runs.
5. **Feature Selection:** Integrate CatBoost’s `select_features` or SHAP-based selection after each training. Use it once per fold to drop weak features before final training on that fold.
6. **Hyperparameter Loop:** Add an inner loop or `GridSearchCV` (with TimeSeriesSplit) to tune CatBoost params. Limit trials and consider Bayesian/halving.
7. **Experiment Runs:** Execute the grid of configurations as planned. Store all results (metrics, chosen features, hyperparams) for analysis.
8. **Analyze and Choose:** Compare schemes via summary tables and stability diagnostics. Choose the method (e.g. rolling W=..., embargo=..., etc.) that balances performance with consistency.
9. **Finalize and Deploy:** Retrain the selected model on all training data, validate on final holdout, and then deploy. Continue monitoring live performance vs. expectations.

**Pseudocode Example (Polars) – Rolling Walk-Forward:**
```python
import polars as pl
from catboost import CatBoostRegressor, Pool

df = pl.read_csv("data.csv").sort("timestamp")  # assume sorted by time
df = df.with_columns([
    # e.g. compute lags or rolling stats here
])
train_window = 365  # days
test_window = 30    # days
step = 30           # move forward by one month each fold

for start in range(0, len(df) - train_window - test_window + 1, step):
    train_df = df.slice(start, train_window)            # past N days
    test_df = df.slice(start+train_window, test_window) # next M days

    train_pool = Pool(train_df.drop("target"), train_df["target"])
    test_pool = Pool(test_df.drop("target"), test_df["target"])

    # Purge: remove overlaps if label horizon spans multiple days
    # (skip here if already aligned)

    # Hyperparameter tuning (example grid search):
    best_model = None; best_score = -float('inf')
    for depth in [4,6,8]:
        for lr in [0.01, 0.03, 0.1]:
            model = CatBoostRegressor(depth=depth, learning_rate=lr, has_time=True,
                                       iterations=500, random_seed=0)
            model.fit(train_pool, eval_set=test_pool, verbose=False)
            score = model.get_best_score()['validation']['RMSE']  # or another metric
            if score > best_score:
                best_score = score; best_model = model

    preds = best_model.predict(test_pool)
    # Evaluate preds vs test_df["target"], compute PnL, etc.
```

Note how **has_time=True** is set to ensure CatBoost respects order.  In practice, replace the naive grid loop with Optuna or CatBoost’s built-in `randomized_search` for efficiency.

By following the above roadmap—with careful cross-validation design, leakage guards, and alignment of metrics to trading goals—you will turn the current disorganized pipeline into a systematic, stable walk-forward framework.  The combined references above provide the theoretical and practical foundation: López de Prado’s techniques, recent empirical studies, and best-practice guides.  Experiment thoroughly, document results, and iterate on the recommended defaults until the model’s performance is both robust and economically meaningful.

**Sources:** Time-series CV and leakage methods; CatBoost specifics (has_time, select_features, border_count); Trading ML best practices.