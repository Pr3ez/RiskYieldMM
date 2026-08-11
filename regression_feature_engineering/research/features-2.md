# Executive Summary

**Context & Goals:** We survey methods to enrich minute-level trading data with multi–timeframe and cross–asset features, avoiding lookahead/overlap.  This involves constructing rolling windows (e.g. 5 min, 15 min, 1 h, 4 h, 8 h) on tick or 1-min bars, and engineering features (OHLCV, returns, volatility, orderbook proxies, etc.) from each horizon.  We also fuse data from multiple instruments (crypto, FX, commodities, indices) via spreads/ratios, cointegration, or statistical composites.  Key concerns include *temporal alignment* (using backward-looking “as-of” joins to prevent leakage【7†L456-L460】【17†L57-L65】), *normalization* (making features price-agnostic via returns or z-scores【21†L79-L87】), *feature decorrelation/dimensionality reduction* (e.g. PCA on correlated instruments), and *real-time constraints* (incremental updates, feature stores).  We recommend concrete algorithms (pseudocode) to update multi-timeframe aggregations in streaming fashion, methods for safe cross-asset signal creation, a unified feature schema, and robust validation protocols (walk-forward tests, ablation, statistical significance). 

【36†embed_image】 *Figure 1: Example multi-timeframe market data. A high-resolution (1-min) candlestick chart on tablet is shown alongside broader views; each minute’s features would include aggregates from higher windows (5m, 15m, etc.) giving context. Combining such multi-scale signals can improve predictive power【26†L29-L32】.*

# 1. Multi-Timeframe Feature Engineering

**Time Aggregation & Rolling Windows:** To attach higher-timeframe context to each 1-min bar without lookahead, one typically *aggregates past data only*.  For example, a 5-min feature at 10:01 should use data from 09:56–10:00 (the last complete 5-min block) or the last 5 one-minute bars.  A common approach is to maintain rolling windows of the last *n* 1-min bars.  For each new minute’s bar, one updates all windows and computes features.  Edge cases (e.g. missing minutes due to illiquidity) should be handled by **forward-filling** or marking gaps.  If a market closes (holidays, weekends), one must skip or impute those spans carefully.  When aggregating tick data to minute bars, using **fixed intervals** (e.g. each minute aligned to clock) ensures consistency, but one may also consider *volume* or *tick* bars to avoid uneven tick counts.

**Alignment & Labeling:** Crucially, features from slower timeframes must be *lagged* to avoid peeking.  Practically, this means using a backward-looking “as-of” join: at each minute $t$, we merge the latest available 5-min/15-min/etc. aggregates whose end timestamps $\le t$.  This guarantees only *closed* candles contribute【7†L456-L460】【17†L57-L65】.  In pandas/polars this is done via `merge_asof` or `join_asof` on timestamps with `direction="backward"`, then forward-filling missing values.  For example, pre-compute OHLCV bars at 5m, 15m, etc., then as-of join them to the 1-min index.  This ensures each row’s features reflect only past information【7†L456-L460】.  When implementing streaming, one can equivalently update features on-the-fly per new bar (see next section).  

**Resampling Bias & Sampling:** Aggregating irregular ticks into fixed bars can introduce bias if, e.g., sudden price jumps occur mid-bar.  Using ticks avoids some bias but increases data volume.  A compromise is 1-min bars as a base resolution (or volume bars).  Whatever the base (tick or min-bar), **consistent clock alignment** avoids mismatches across assets.  All time series should be on the same time grid (UTC is common) before as-of joining【7†L456-L460】.  Missing data (e.g. stale quotes) can be forward-filled; but one must not backward-fill future data.  

**Feature Types (per timeframe):** From each window (e.g. last 5m, 15m, 1h, …) compute a variety of signals:  
- **OHLCV Aggregates:** e.g. open, high, low, close, sum(volume) of that window.  
- **Returns & Ratios:** e.g. log returns over the window, or returns relative to longer trend.  
- **Volatility:** e.g. ATR (average true range), standard deviation of returns, high-low range.  
- **Momentum/Trend:** e.g. moving-average crossovers, EMA differences (short vs long), RSI or other bounded oscillators.  
- **Market Microstructure:** for assets with orderbook data, proxies like bid-ask spread, order imbalance, execution flow.  (Even for minute data, volume imbalance or tick counts can hint at pressure.)  
- **Seasonality & Calendars:** dummy features for hour-of-day, day-of-week, month, trading-session boundaries.  E.g. time-of-day matters for equities/FX (lunch dips, open/close auctions) and day-of-week (weekend gaps in FX/crypto, monthly cycles in indices).  Calendar effects (e.g. quarter-end, FOMC days) can also be encoded as features.  
- **Spreads/Cross-Asset:** (Discussed below) differences or ratios between assets to capture relative moves.  

**Implementation in Streaming:** In practice, one can implement the above by maintaining stateful buffers per timeframe. For instance, a Python/polars pseudocode approach:   

```python
from collections import deque

# Define higher-timeframe lengths (in minutes)
window_minutes = [5, 15, 60, 240, 480]  # 5m, 15m, 1h, 4h, 8h
# Buffers to hold recent minute-bars for each window
buffers = {w: deque(maxlen=w) for w in window_minutes}

current_bar = {"open": None, "high": -inf, "low": +inf, "close": None, "volume": 0}
last_minute = None

def on_tick(tick):
    """Process each incoming tick (timestamped price & volume)."""
    global current_bar, last_minute
    minute = tick.timestamp.floor("1min")

    # If a new minute has started, finalize the last 1-min bar
    if last_minute is not None and minute != last_minute:
        # Add finished bar to each rolling window
        finished = current_bar.copy()
        for w, buf in buffers.items():
            buf.append(finished)
        # Compute features for the *closed* minute last_minute
        feat = compute_features(finished, buffers)
        emit(feat)  # output or store features for modeling

        # Start new bar
        current_bar = {"open": tick.price, "high": tick.price,
                       "low": tick.price, "close": tick.price,
                       "volume": tick.volume}
        last_minute = minute
    else:
        # Still in the same minute: update OHLCV
        if current_bar["open"] is None:
            current_bar["open"] = tick.price
        current_bar["high"] = max(current_bar["high"], tick.price)
        current_bar["low"]  = min(current_bar["low"], tick.price)
        current_bar["close"] = tick.price
        current_bar["volume"] += tick.volume
        last_minute = minute
```

Each time a 1-min bar closes, we append it to all buffer deques.  Once a buffer of length *w* is full, one can compute e.g. a 5-min aggregate from `buffers[5]`.  In practice, one often computes features on each tick or each minute by rolling, but this example flushes at minute boundaries.  Polars (a Rust-based DataFrame library) can assist with efficient time-based grouping: for static data, `groupby_dynamic` can aggregate minute bars into coarser bars, and `join_asof` aligns them【7†L456-L460】.  In streaming, one implements the above logic or uses a stream framework (Kafka/Flask) with sliding-window operators.  **Key edge-case:** If a minute has no ticks (zero volume), `current_bar` may remain open; one should decide to forward-fill `close` or drop that timestamp.

**Mermaid: Multi-Timeframe Processing Flow**

```mermaid
flowchart TD
    T[Tick Stream (timestamp, price, volume)] --> B1[1-min Bar Builder]
    B1 --> F1[Compute 1-min OHLCV]
    F1 --> W5[Rolling 5-min Window]
    F1 --> W15[Rolling 15-min Window]
    F1 --> W60[Rolling 60-min Window]
    %% intermediate windows omitted for brevity
    W5 --> M5[5-min Aggregates]
    W15 --> M15[15-min Aggregates]
    W60 --> M60[60-min Aggregates]
    %% merging back:
    M5 --> |As-of Join| J1[Merge 5m features into 1-min frame]
    M15 --> |As-of Join| J1
    M60 --> |As-of Join| J1
    J1 --> F[Feature Vector with Multi-Scale Context]
    click J1 href "#" "See caption on as-of join usage【7†L456-L460】"
```

This flowchart illustrates that every tick is binned into 1-min bars; those feed into rolling windows (5m,15m,1h, etc.) which produce their own aggregated bars, then an *as-of join* merges them back to the 1-min timeline so that each minute has a contextual feature vector【7†L456-L460】.

# 2. Cross-Asset Feature Construction

**Spread and Ratio Features:**  To capture inter-market relationships (e.g. BTC vs ETH, S&P vs Nasdaq, crude vs gold, USD vs JPY), construct features like **price spreads** or **price ratios**.  For a cointegrated pair (e.g. futures spreads), use the difference (e.g. *spread = P_A – P_B*) or normalized ratio (e.g. *ratio = P_A/P_B*).  Such spreads often mean-revert; one can include their past values, returns, or volatility.  For unbounded assets, use log ratios or orthonormal transformations to avoid scale issues.  Example: include `log(BTC) – log(ETH)` or `BTC/ETH` over rolling windows.  

**Cointegration & Error-Correction:** If two assets (like ES and NQ, or gold and silver) are known to cointegrate, we can apply an **error-correction feature**: fit a linear regression or Engle–Granger model and use the residual (the distance from long-term equilibrium) as a feature.  This equilibrium error often has predictive value【24†L24-L32】.  For instance, if *a·P_A – b·P_B* drifts, the Z-score of that linear combination (or its one-period change) can signal reversion.

**Lead-Lag Relationships:** Empirically, some instruments lead others.  One can quantify this with cross-correlation or Granger causality, then include lagged versions of leading assets.  For example, if **EUR/USD** historically leads **USD/JPY** by a few minutes under certain regimes, include features like `return_EURUSD_{t-Δ}` as input for predicting USD/JPY at time *t*.  In practice, one might *dynamically detect* lags (e.g. by windowed cross-correlation) and then periodically update the lag values in features.  Studies find that “information from one asset’s prices and order-book imbalance predicts another’s future behavior”【23†L42-L51】.  Thus, for related pairs (equity indices, commodities vs currencies, crypto vs tech stock), we can include the other asset’s recent returns/indicators shifted by the estimated lag.  

**Principal Component / Factor Features:**  For clusters of instruments (e.g. ES & NQ, EURUSD & other majors, gold & silver futures), one can apply **PCA or factor analysis** on their returns to capture common modes.  The first principal component (or a small number of components) can serve as a cross-asset “market mode” feature.  This reduces dimensionality and encapsulates shared movement.  For example, computing PCA on minute returns of several commodity futures yields factors that can feed into each instrument’s model.  Alternatively, Independent Component Analysis (ICA) or clustering can find decorrelated factors.  Quantreo’s analysis shows that after converting to *relative* features, z-scoring them makes cross-asset models more robust【21†L79-L87】, effectively a form of normalization plus dimension reduction.  

**Liquidity & Volatility Proxy Features:**  Cross-asset influences also arise via liquidity.  Including features like total traded volume (in USD) across assets, or volatility of a correlated market, can be insightful.  E.g. a surge in **VIX** (implied volatility index) often precedes equity index moves; a feature `VIX_t` or recent changes in VIX could be added to ES/NQ models.  Similarly, **carry/interest effects** (like 2-point interest-rate differential for EURUSD) can be features for FX, though these are longer-horizon signals.

# 3. Normalization, Scaling, and Decorrelating

**Price-Agile Features:** Because price levels differ dramatically (BTC~$50k, EURUSD~1.10, oil~$75, etc.), raw price features are not comparable.  We generally convert features into *price-agnostic forms*:  
- **Returns/Pct Changes:** e.g. log-returns or percent-change over windows.  
- **Ratios:** e.g. relative differences (EMA_fast / EMA_slow), or normalized momentum (price / moving average – 1).  
- **Bounded Oscillators:** like RSI or ADX (range 0–100 or 0–1).  

These ensure signals reflect *behavior* not scale【21†L79-L87】【7†L555-L564】.  For example, a 100-point rise in ES (0.5%) is normalized differently than a 100-point rise in oil (133%).  Most feature engineering frameworks convert OHLC to returns or percentage bands.  

**Z-Score and Rolling Standardization:** Within each asset, one often standardizes features by a rolling mean and std (e.g. 30-day or 1-month window) to capture regime changes.  However, care must be taken *not to peek into the future*: the rolling parameters should be computed using only past data (no leakage).  Alternatively, one can precompute static normalization factors (e.g. annualized volatility) to avoid live recalculation【26†L117-L124】.  For cross-asset consistency, one may then map each asset’s features to a common distribution: e.g. by rank-normalizing each feature across assets or converting to percentiles.  

**Cross-Asset Alignment:** To allow pooling data from different assets, use transformations that make features comparable.  One approach (Quantreo) is to express each asset’s feature as a ratio vs. its own scale (e.g. dividing by recent volatility or a long-term mean) and then z-score【21†L79-L87】.  The unified schema then has features like `{asset, feature_name, value}` where `value` is on a common scale.  This prevents a model from simply learning “BTC is expensive” or “EURUSD moves slowly” by focusing on standardized signals.  

**Feature Correlation & Dimensionality Reduction:** Raw feature sets (especially across multiple timeframes) can be highly redundant.  For example, a 5-min and a 10-min moving average are often correlated.  To decorrelate, one may apply PCA on the feature matrix, drop features with near-zero variance, or use feature selection (e.g. L1-regularization, mutual information ranking) to prune.  Another tactic is *target-independent factor models*: cluster features into groups (momentum, volatility, seasonality) and within each group remove the mean.  In practice, including PCA or ICA components as features can capture multi-asset commonality while excluding idiosyncratic noise.

# 4. Deployment Considerations

**Streaming Computation:** In production, features must be updated in real time.  Frameworks like Kafka, Flink, or in-memory databases can maintain rolling windows and compute aggregates with low latency.  Each new tick/minute triggers incremental updates rather than full re-computation.  The algorithms above (with deques or differential updates) work in constant time per update.  Avoid holding full historical series in memory – keep only as much history as needed (e.g. max 1 day or longest window).  Feature stores (e.g. Feast, Tecton) may be used to serve pre-computed features to models in production.  

**Latency & Memory:** Multi-timeframe features are generally light to compute if only short windows are needed.  The main cost is I/O (ingesting tick streams) and join overhead if syncing assets.  One should ensure time alignment efficiently (e.g. indexing by integer minute).  Memory can be managed by discarding old bars beyond window length.  For ultra-low latency (sub-second), one might limit to only the fastest windows (skip 8h features in a high-frequency model).  

**Backtesting & Validation:** Careful validation is essential. Always split data temporally (no shuffling) and simulate forward testing.  When merging features, use the as-of join logic to avoid lookahead – never use future information for an earlier timestamp【7†L456-L460】.  Employ walk-forward cross-validation (rolling origin) to assess stability across regimes.  **Ablation tests** (removing one class of features, e.g. all 4h features) can quantify marginal benefit.  **Metrics:** Evaluate feature importance (e.g. t-test on feature-target correlation, or SHAP values) and model performance (Sharpe, accuracy, F1, etc.).  Perform statistical tests (e.g. checking feature means vs zero, stationarity tests on features, consistency of betas over time) to ensure signals are robust.  Monitor for overfitting by comparing in-sample vs out-of-sample performance.  

**Statistical Significance:** For each engineered feature, test its predictive value.  For example, correlate a feature with future returns and test if the correlation is significantly different from zero.  Check consistency: does a feature's rank or sign remain stable across market regimes?  Use rolling windows to test stability (e.g. compute t-stat of feature in sliding windows) and discard features that flip unpredictably.

# 5. Feature Catalog and Schema

We propose a **unified schema** (wide table) where each row is (asset, timestamp, [features…]).  Features have standardized names with time suffixes (e.g. `rsi_15m`, `vol_1h`, `spread_ES_NQ`) and values normalized as above.  Below is a **recommended feature list** by category, with applicability:

| **Feature Category**  | **Example Feature**             | **Description / Assets**                                 |
|-----------------------|---------------------------------|----------------------------------------------------------|
| **Base OHLCV**        | `open_1m, high_1m, low_1m, close_1m, vol_1m` | 1-min bar values (all assets). Raw inputs.                       |
| **Returns**           | `ret_1m, ret_5m, ret_1h`        | Percent or log-return over 1-min, 5-min, 1h windows (all assets).   |
| **Volatility**        | `atr_5m, std_15m, highlow_1h`   | Volatility measures (ATR, stdev of returns, high–low range) per window (all assets). |
| **Momentum/Trend**    | `ema_diff_15m, ma_cross_1h`     | Difference or crossover of EMAs/SMAs (e.g. 12-EMA minus 26-EMA over 15m) (all assets). |
| **Oscillators**       | `rsi_5m, stoch_%K_1h`          | Oscillators (RSI, Stochastic) over various windows (all assets).     |
| **Orderflow/Micro**   | `tick_imbalance, order_spread`  | Order book imbalances or bid-ask spread proxies (crypto, futures).  |
| **Seasonality**       | `hour_of_day, day_of_week, is_month_end` | Categorical/time features (all assets; adjust for market hours). |
| **Cross-Asset Spreads** | `BTC_ETH_price_diff, EURUSD_USDJPY_ratio` | Differences/ratios of related pairs (crypto, FX).            |
| **Commodity Spreads** | `gold_oil_ratio`              | e.g. GC/CL price ratio (metals vs energy).                   |
| **Index Diff**        | `ES_NQ_spread`                | ES minus NQ futures (equity index pair).                    |
| **Cointegration Residuals** | `ES_NQ_coinv_err`        | Error from regression ES~NQ (if cointegrated).              |
| **Lead-Lag Lags**     | `EURUSD_lag1_ret`             | Past returns of leading asset (for discovered lags).        |
| **Liquidity**         | `volumebucket, trade_count`   | High-frequency volume in each bar or #trades (all assets).  |
| **Normalization**     | `zscore_ret_1h`              | Z-scored returns (per asset, using rolling mean/stdev).     |
| **PCA Components**    | `pca1_index, pca2_currency`   | Principal components across groups (equity indices, FX).    |

Each feature column is applied to relevant assets (e.g. OSCILLATORS for all, Orderflow for those with orderbook).  The schema remains consistent: one row per (asset, minute), features as above.  For cross-asset features (e.g. spreads), one could either: (a) assign them to one of the pair’s tables with the other asset as context, or (b) maintain a separate “spread table” keyed by timestamp.  In practice we can simply duplicate the spread features into both asset tables with a common timestamp.

# 6. Evaluation & Validation Plan

- **Backtesting:** Use a strict **time-series split** (walk-forward).  For example, train on Year N, test on N+1, roll forward.  Ensure any standardization (e.g. z-scores) is fitted only on training window.  **No lookahead:** Do not sample a future bar to compute past features.  Use as-of joins or streaming methods to simulate real-time feature availability【7†L456-L460】.
- **Metrics:** Evaluate model predictions via accuracy (for classification signals), Sharpe ratio or mean return (for regression/prediction), precision/recall (for signals).  Use **out-of-sample performance** to gauge real utility.
- **Ablation Tests:** Systematically disable one group of features (e.g. remove all cross-asset features, or all >1h features) to see impact on performance.  This isolates the *marginal contribution* of feature types.
- **Stability Checks:** Compute, for each feature, the autocorrelation and cross-validated stability of its predictive power.  If a feature’s importance or sign flips wildly over time, it may be fragile.  Perform **statistical tests** (t-test or permutation) to see if a feature’s correlation with the target is significantly non-zero.
- **Lead-Lag Confirmation:** If using inferred lags, re-test cross-correlation periodically (e.g. monthly) to ensure the presumed leader remains ahead.
- **Calibration:** Check that combining cross-asset features does not cause multicollinearity.  Use variance inflation factor (VIF) diagnostics or remove near-duplicate signals.

# 7. Figures & Visual Aids

- **Multi-Timeframe Alignment:** A timeline chart can illustrate how a 5-min bar (e.g. 09:55–10:00) aligns relative to minute ticks.  Each minute’s features should reflect the last fully closed 5-min, 15-min, etc. (A *Mermaid sequence/timeline* is shown above.)
- **Lead-Lag Example:** An illustrative plot (not shown) could overlay two price series (e.g. ES vs NQ) highlighting a consistent lag of, say, 1 minute.  Alternatively, a *cross-correlation graph* vs lag can show the optimal offset.
- **Feature Importance Heatmap:** A diagram showing feature importances by asset and timeframe can guide which horizons matter for which markets.

# 8. Key References

- Lopez de Prado, M. *Advances in Financial Machine Learning.* Wiley, 2018. (Chapter on **feature engineering** and labeling techniques.)  
- Zhang et al. (2025). *Neural Network-Based Algorithmic Trading: Multi-Timeframe Analysis in Crypto.* arXiv:2508.02356.【26†L29-L32】 (Demonstrates integration of minute, hourly, daily data and external signals for crypto, emphasizing normalization and real-time execution).  
- Schmidt et al. (2024). *Lead-Lag Relationships in Market Microstructure.* SSRN. (Findings: cross-asset lead-lag via price, order imbalance; most leads among related instruments)【23†L42-L51】.  
- Troster et al. (2022). *Cointegration and lead-lag between industry portfolios and market.* J. Int. Money Finance. (Shows predictive power of cointegration residuals).  
- *Multi-Timeframe Feature Engineering for Bitcoin* (2026 preprint)【7†L456-L460】【7†L555-L564】. (Describes backward-looking as-of joins for merging timeframes and normalization of features across scales).  
- Quantreo (2024). *Multi-Asset Feature Engineering Tutorial*【21†L79-L87】. (Recommends relative transformations and z-scoring to harmonize features across assets of different price scales).  
- Pathway Docs: *ASOF Join Tutorial* (2023). (Illustrates as-of join usage for aligning streams of different frequencies【17†L57-L65】).  
- Exchange Data Guides (e.g. CME/ICE spec sheets for ES, GC, CL) for details on trading hours, tick sizes, and session breaks.  
- Jackson & Parker (2018). *Financial Time Series and Monte Carlo Methods.* (Sections on data granularity, sampling bias, and return computation.)

Each of these emphasizes careful temporal alignment, normalization, and statistical validity – principles central to our framework. 

