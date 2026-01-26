# LSTM Model Reference

**Official Documentation:** https://pytorch.org/docs/stable/generated/torch.nn.LSTM.html

## Algorithm Overview

**LSTM** (Long Short-Term Memory) is a recurrent neural network architecture.

### How It Works

1. **Sequential Processing**: Reads data one timestep at a time
2. **Memory Cells**: Maintains long-term state across timesteps
3. **Gates**: Controls what to remember/forget (input, forget, output gates)
4. **Hidden State**: Carries temporal information forward

### Architecture (Your Config)

```
Input → [LSTM Layer 1] → [LSTM Layer 2] → [Fully Connected] → Output
  ↓           ↓               ↓
seq_len    hidden_size     n_classes (or 1)
 (20)        (64)
```

### Unidirectional Only!

**Never use Bidirectional LSTM for forecasting** - it peeks into future data.
- BiLSTM processes forward AND backward
- Only appropriate for sequence classification where full sequence is known
- For prediction tasks: always unidirectional

### Why LSTM for Time Series?

| Tree Models | LSTM |
|-------------|------|
| See features as independent | **Sees temporal sequence** |
| No memory of past | **Explicit memory mechanism** |
| Good at feature interactions | **Good at temporal patterns** |

---

## Your Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `train_window` | 600 | Samples in training window (larger for LSTM) |
| `train_ratio` | 0.70 | Portion for training |
| `val_ratio` | 0.15 | Portion for validation |
| `cal_ratio` | 0.15 | Portion for conformal calibration |
| `embargo_bars` | 24 | Gap between splits |
| `feature_selection` | "variance" | Variance-based (no tree importance) |
| `feature_selection_ratio` | 0.8 | Keep top 80% features |
| `min_features` | 40 | Minimum features |

**Note:** Larger window (600 vs 400) because LSTM needs more data to learn sequences.

Reference: [lstm_model.py#L63-105](../../scripts/target_models/validation/backtest/models/lstm_model.py)

---

## Model Hyperparameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `hidden_size` | 64 | LSTM hidden state dimension |
| `num_layers` | 2 | Stacked LSTM layers |
| `learning_rate` | 0.001 | Adam optimizer LR |
| `epochs` | 100 | Training epochs |
| `batch_size` | 32 | Mini-batch size |
| `dropout` | 0.2 | Regularization dropout |
| `seq_len` | 20 | **Lookback window** (key param!) |
| `device` | "auto" | "cuda" / "cpu" |

Reference: [lstm_model.py#L73-94](../../scripts/target_models/validation/backtest/models/lstm_model.py)

---

## Sequence Creation

**Critical concept:** LSTM needs sequential data, not flat features.

```python
# Input: X (n_samples × n_features)
# Output: X_seq (n_samples × seq_len × n_features)

# For sample at time t:
# X_seq[t] = [X[t-19], X[t-18], ..., X[t-1], X[t]]  # 20 timesteps
```

This means:
- First `seq_len - 1` samples are dropped (no history)
- Each sample carries 20 bars of context

### Input Shape Convention
```python
# PyTorch default: (seq_len, batch, features)
nn.LSTM(input_size, hidden_size, batch_first=False)

# batch_first=True: (batch, seq_len, features) - more intuitive
nn.LSTM(input_size, hidden_size, batch_first=True)  # Recommended
```

### Variable-Length Sequences
For sequences of different lengths in same batch:
```python
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

# Pad shorter sequences with zeros
padded_seqs = pad_sequence(sequences, batch_first=True, padding_value=0)

# Pack to ignore padded timesteps during LSTM forward
packed = pack_padded_sequence(padded_seqs, lengths, batch_first=True, enforce_sorted=False)
output, (h_n, c_n) = lstm(packed)

# Unpack for downstream processing
output_unpacked, _ = pad_packed_sequence(output, batch_first=True)

# Mask padded positions in loss computation!
loss = masked_loss(output_unpacked, targets, mask)
```

Reference: [lstm_model.py#L260-295](../../scripts/target_models/validation/backtest/models/lstm_model.py)

---

## Optuna Search Space

| Parameter | Range/Options | Description |
|-----------|---------------|-------------|
| `hidden_size` | [32, 64, 128] | Categorical |
| `num_layers` | 1-3 | Integer (deeper = harder to train) |
| `learning_rate` | 0.0001-0.01 | **Log scale** |
| `dropout` | 0.1-0.4 | Between layers |
| `seq_len` | [10, 20, 30, 50] | Lookback window (critical) |
| `batch_size` | [16, 32, 64] | Smaller often better for sequences |

**Tuning settings:**
- Trials: 10 (fewer because LSTM is slow)
- Timeout: 60 seconds (longer for LSTM)
- Epochs during tuning: 20 (reduced for speed)

**Sequence length guidance:**
- Start with pattern length (e.g., 12 for monthly with yearly seasonality)
- Too short: misses long-term dependencies
- Too long: harder to train, risk overfitting
- Treat as key tunable parameter

Reference: [lstm_model.py#L350-430](../../scripts/target_models/validation/backtest/models/lstm_model.py)

---

## Classification vs Regression

| Aspect | Classification | Regression |
|--------|---------------|------------|
| Model class | `LSTMClassifier` | `LSTMRegressor` |
| Output layer | `Linear(hidden, n_classes)` | `Linear(hidden, 1)` |
| Loss function | `CrossEntropyLoss` | `MSELoss` |
| Optuna metric | Accuracy | -MSE |
| Output | Class logits → softmax | Single value |

### Classification Architecture
```python
class LSTMClassifier(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers, n_classes, dropout):
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, ...)
        self.fc = nn.Linear(hidden_size, n_classes)  # Multi-class output
```

### Regression Architecture
```python
class LSTMRegressor(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers, dropout):
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, ...)
        self.fc = nn.Linear(hidden_size, 1)  # Single output
```

Reference: [lstm_model.py#L205-255](../../scripts/target_models/validation/backtest/models/lstm_model.py)

---

## Feature Selection

**Method:** Variance-based (LSTM has no tree importance)

```python
variances = X_train.var()
selected_features = variances.nlargest(n_keep).index.tolist()
```

**Why variance?** High-variance features carry more signal for neural networks.

Reference: [lstm_model.py#L130-155](../../scripts/target_models/validation/backtest/models/lstm_model.py)

---

## Data Preprocessing

**StandardScaler required:** Neural networks need normalized inputs.

```python
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_val_scaled = scaler.transform(X_val)  # Same transform!
```

### Missing Data Handling
LSTMs don't handle NaN internally - you must address it:

```python
# Option 1: Imputation (common)
X_filled = X.fillna(method='ffill')  # Forward fill

# Option 2: Indicator feature (model learns to down-weight)
X['feature_missing'] = X['feature'].isna().astype(int)
X['feature'] = X['feature'].fillna(0)  # Fill with 0 after standardization

# Option 3: Masking layer (Keras-style, PyTorch requires manual mask)
```

### Temporal Feature Engineering
Add time-derived features to help LSTM learn patterns:

```python
import numpy as np

# Cyclical encoding (respects that 23:00 is close to 00:00)
df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
```

### Series Transformations
```python
# Differencing for stationarity
df['price_diff'] = df['price'].diff()

# Log transform for multiplicative series
df['price_log'] = np.log(df['price'])

# Remember to invert at output!
```

---

## Trade-offs

| Strength | Weakness |
|----------|----------|
| ✅ **Captures temporal patterns** | ❌ **Slowest model** |
| ✅ Memory mechanism | ❌ Needs more data (longer window) |
| ✅ Non-linear temporal relationships | ❌ Harder to interpret |
| ✅ Can model regime transitions | ❌ Risk of vanishing gradients |
| ✅ GPU acceleration | ❌ More hyperparameters |

---

## GPU Usage

```python
device = "cuda" if torch.cuda.is_available() else "cpu"
model = LSTMClassifier(...).to(device)
X_tensor = X_tensor.to(device)
```

**Memory:** ~0.5-1GB VRAM

---

## Training Techniques

### Gradient Clipping (Essential)
```python
optimizer.zero_grad()
loss.backward()
torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)  # Prevent explosion
optimizer.step()
```
- LSTMs can have exploding gradients despite gating
- Clip to threshold (5-10 typical)
- If frequently hitting clip: LR too high or model needs regularization

### Early Stopping
```python
best_val_loss = float('inf')
patience_counter = 0
for epoch in range(max_epochs):
    val_loss = evaluate(model, val_loader)
    if val_loss < best_val_loss:
        best_val_loss = val_loss
        patience_counter = 0
        save_checkpoint(model)
    else:
        patience_counter += 1
        if patience_counter >= patience:
            break  # Early stop
```

### Truncated BPTT (Long Sequences)
For very long sequences, backprop through all timesteps is memory-intensive:
```python
hidden = None
for chunk in split_sequence(data, chunk_size=50):
    output, hidden = model(chunk, hidden)
    loss.backward()
    hidden = (hidden[0].detach(), hidden[1].detach())  # Break gradient chain
```
- Hidden state persists (memory continues)
- Gradients only flow back `chunk_size` steps
- Reduces memory, stabilizes learning

### Teacher Forcing (Multi-step Forecasts)
For decoder-style multi-step prediction:
- **With teacher forcing:** Feed actual previous value as input
- **Without:** Feed model's own prediction

```python
teacher_forcing_ratio = 0.5  # Start high, decay over training
use_teacher = random.random() < teacher_forcing_ratio
input_t = actual_prev if use_teacher else predicted_prev
```
- Pure teacher forcing → model struggles at inference (never saw own errors)
- No teacher forcing → slow convergence
- Solution: scheduled decay from 1.0 → 0.0 during training

### Stateful vs Stateless Training
| Mode | Hidden State | When |
|------|-------------|------|
| **Stateless** | Reset to zero each batch | Multiple independent sequences |
| **Stateful** | Carry over between batches | One long continuous sequence |

For walk-forward: typically stateless (each window is independent sample)

### Batch Size Considerations
| Batch Size | Effect |
|------------|--------|
| Small (8-32) | Better generalization, captures temporal variability, slower training |
| Large (64-256) | Faster training, may average out patterns, less noisy gradients |
| 1 (online) | Noisiest but adapts quickly, ensure more epochs |

**Sequence models often prefer smaller batches** than other neural networks.

If using very small batch sizes, compensate with more training epochs.

---

## Optimizer Choices

| Optimizer | When to Use |
|-----------|-------------|
| **Adam** | Default, good out-of-box |
| **RMSprop** | Hinton's RNN recommendation |
| **SGD+momentum** | Can achieve better final results with careful LR tuning |

**Learning rate schedule:**
- `ReduceLROnPlateau`: reduce when validation loss plateaus
- Typical: reduce by 0.5 after N epochs no improvement

---

## Regularization

| Technique | Implementation |
|-----------|---------------|
| **Dropout** | Between LSTM layers (PyTorch `dropout` param) |
| **Weight decay** | L2 regularization via optimizer |
| **Layer norm** | After LSTM outputs (stabilizes training) |
| **Gradient clipping** | Caps extreme updates |

**Dropout in LSTM:**
- PyTorch applies dropout **between layers** (not on recurrent connections)
- Only works when `num_layers > 1`
- Start with 0.1-0.3, increase if overfitting

---

## Loss Functions

### Regression
| Loss | When to Use |
|------|-------------|
| `MSELoss` | Default, optimizes RMSE |
| `L1Loss` (MAE) | Robust to outliers, optimizes median |
| `HuberLoss` | Blend of MSE/MAE, good for outlier-prone data |

### Classification
| Loss | When to Use |
|------|-------------|
| `CrossEntropyLoss` | Multi-class (combines LogSoftmax + NLLLoss) |
| `BCEWithLogitsLoss` | Binary (more stable than BCELoss) |

---

## Multi-Step Forecasting Strategies

### Direct Multi-Horizon
```python
# Single LSTM outputs all H steps at once
class LSTMDirectMultiStep(nn.Module):
    def __init__(self, input_size, hidden_size, H):
        self.lstm = nn.LSTM(...)
        self.fc = nn.Linear(hidden_size, H)  # H outputs
```
- Simple, single forward pass
- Works well for small H (3-5 steps)
- Doesn't model dependencies between output steps

### Recursive (Iterative)
```python
# Use one-step model repeatedly
for t in range(H):
    pred_t = model(input_seq)
    predictions.append(pred_t)
    input_seq = update_with_prediction(input_seq, pred_t)  # Feed back
```
- Errors compound with each step
- Model never saw its own errors during training
- Use teacher forcing to mitigate (see Training Techniques)

### Encoder-Decoder (Seq2Seq)
```python
# Encoder compresses history, Decoder generates future
encoder_hidden = encoder(X_history)
for t in range(H):
    decoder_output, decoder_hidden = decoder(prev_output, decoder_hidden)
```
- Most flexible for long horizons
- Can use attention for better long-sequence handling
- Harder to train (two RNNs)

---

## Output Post-Processing

### Inverse Transforms (Critical!)
```python
# If you scaled inputs, MUST invert predictions
predictions_unscaled = scaler.inverse_transform(predictions)

# If you differenced, add back the last known value
predictions_level = predictions_diff + last_actual_value

# If you log-transformed
predictions_original = np.exp(predictions_log)
```
**Always compute metrics on de-normalized predictions!**

### Output Activation Functions
| Task | Output Activation |
|------|------------------|
| Regression (unbounded) | None (linear) |
| Regression [0,1] | Sigmoid |
| Regression [-1,1] | Tanh |
| Multi-class classification | None (CrossEntropyLoss includes softmax) |
| Binary classification | None (BCEWithLogitsLoss includes sigmoid) |

---

## Advanced Enhancements

### Attention Mechanism
Add attention to focus on relevant timesteps:
```python
# After LSTM outputs all timesteps
attn_weights = softmax(linear(lstm_outputs))  # Learn importance per timestep
context = sum(attn_weights * lstm_outputs)    # Weighted combination
final_output = fc(context)
```
- Helps with long sequences
- Provides interpretability (which timesteps matter)
- Used in Temporal Fusion Transformer

### CNN-LSTM Hybrid
```
Input → [Conv1D] → [MaxPool] → [LSTM] → [FC] → Output
```
- CNN extracts local patterns (short-term spikes, motifs)
- LSTM captures long-term dependencies
- Often outperforms pure LSTM
- Good for data with local frequency patterns (sensors, audio)

### Skip Connections (Deep LSTMs)
For >2 layers, add residual connections:
```python
layer1_out = lstm_layer1(x)
layer2_out = lstm_layer2(layer1_out)
final = layer2_out + layer1_out  # Skip connection
```
- Helps gradient flow in deep networks
- Allows stacking more layers

---

## Ensembling LSTMs

### Multiple Initializations
```python
# Train 5 LSTMs with different random seeds
models = [train_lstm(seed=i) for i in range(5)]

# Ensemble prediction = average
predictions = np.mean([m.predict(X) for m in models], axis=0)
uncertainty = np.std([m.predict(X) for m in models], axis=0)
```
- Reduces variance from random initialization
- Standard deviation provides uncertainty estimate
- Simple but effective improvement

### Hybrid Models
```python
# Combine LSTM with classical methods
arima_pred = arima_model.forecast(H)
lstm_pred = lstm_model.predict(X)

final_pred = 0.5 * arima_pred + 0.5 * lstm_pred  # Simple average
# Or: weighted based on recent performance
```
- ARIMA handles linear trends/seasonality
- LSTM handles nonlinear patterns
- M4 competition winner used this approach

### Residual Modeling
```python
# Step 1: Simple baseline forecast
baseline_pred = df['target'].shift(1)  # Naive: last value

# Step 2: Train LSTM to predict residuals
residuals = df['target'] - baseline_pred
lstm_model.fit(X, residuals)

# Step 3: Final forecast = baseline + LSTM correction
final_pred = baseline_pred + lstm_model.predict(X)
```
- Makes LSTM's job easier (only learn what baseline misses)
- Baseline captures major patterns, LSTM refines
- Often improves stability

---

## Probabilistic Forecasting

### Monte Carlo Dropout
```python
model.train()  # Keep dropout ON at inference
predictions = [model(X) for _ in range(100)]  # 100 stochastic passes
mean_pred = np.mean(predictions, axis=0)
std_pred = np.std(predictions, axis=0)  # Uncertainty estimate
ci_90 = (np.percentile(predictions, 5), np.percentile(predictions, 95))
```
- Simple uncertainty estimation
- High variance = model uncertain
- Low variance = confident prediction

### Quantile Outputs
Train LSTM to predict quantiles (0.1, 0.5, 0.9):
```python
class LSTMQuantile(nn.Module):
    def __init__(self, ...):
        self.fc = nn.Linear(hidden_size, 3)  # Lower, median, upper
        
# Use pinball (quantile) loss
def quantile_loss(pred, actual, quantile):
    error = actual - pred
    return torch.max(quantile * error, (quantile - 1) * error)
```
- Distribution-free prediction intervals
- No assumption about error distribution

---

## When to Consider Alternatives

| Situation | Alternative |
|-----------|-------------|
| Very long sequences (>1000 steps) | Transformer, TCN |
| Small dataset (<500 samples) | Tree models, ARIMA |
| Need interpretability | TFT (attention weights) |
| Local patterns important | CNN-LSTM, TCN |
| Training too slow | TCN (parallel), simpler models |
| Multiple seasonalities | N-BEATS, TFT |

**TCN (Temporal Convolutional Network):**
- Dilated convolutions for long memory
- Parallel computation (faster)
- Stable gradients
- Often comparable to LSTM accuracy

**Transformer-based:**
- Direct attention to any timestep (no gradual forgetting)
- Better parallelization
- Higher data requirements
- Examples: TFT, Informer

---

## Why LSTM in Ensemble?

| Tree Models | LSTM |
|-------------|------|
| Static feature view | **Sequential view** |
| Feature interactions | **Temporal dynamics** |
| Good at classification | **Good at regime detection** |

**Ensemble benefit:** Captures patterns trees miss:
- Momentum/trend continuation
- Regime transitions
- Sequential dependencies

---

## Walk-Forward Validation

### Process
1. Train on initial period (e.g., months 1-6)
2. Predict next step (month 7)
3. Reveal actual value for month 7
4. Append to training (now months 1-7)
5. Predict month 8, repeat...

### Implementation
```python
# Rolling forecast evaluation
test_start = train_size
predictions = []

for t in range(test_start, len(data)):
    # Train on all data up to t
    X_train = create_sequences(data[:t], seq_len)
    model = train_lstm(X_train, y_train)
    
    # Predict next step
    X_test = data[t-seq_len:t]  # Last seq_len points
    pred = model.predict(X_test)
    predictions.append(pred)
    
    # In practice: don't retrain every step (expensive)
    # Options: retrain every N steps, or just update state
```

### Expanding vs Fixed Window
| Strategy | Training Set | When |
|----------|--------------|------|
| **Expanding** | All data to date (grows) | Default, assumes patterns persist |
| **Fixed window** | Last W observations (slides) | Concept drift, recent data more relevant |

### Our Pipeline
- Uses `WalkForwardValidator` for proper temporal splits
- Handles sequence creation across split boundaries
- Applies embargo between train/val to prevent leakage

---

## LSTM-Specific Considerations

1. **Sequence gap fix:** When creating val/cal sequences, uses history from previous split
2. **seq_len tuning:** 20 bars = 160 hours of lookback (for 8h bars)
3. **Dropout between layers:** Prevents overfitting on sequential data
4. **Last hidden state:** Only final timestep's hidden state used for prediction
