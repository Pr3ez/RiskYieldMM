"""
LSTM Model Module

Contains LSTM model classes and training functions:
- LSTMClassifier: LSTM for classification tasks
- LSTMRegressor: LSTM for regression tasks
- create_sequences: Create temporal sequences from flat feature matrix
- train_lstm_classifier: Train LSTM classifier with temporal sequences
- train_lstm_regressor: Train LSTM regressor with temporal sequences

Dependencies:
- torch, torch.nn
- sklearn.preprocessing.StandardScaler
- numpy
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler


class LSTMClassifier(nn.Module):
    """LSTM for classification tasks."""

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 64,
        num_layers: int = 2,
        n_classes: int = 2,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = nn.LSTM(
            input_size,
            hidden_size,
            num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        self.fc = nn.Linear(hidden_size, n_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch, seq_len, features) - must be 3D
        # LSTM processes the sequence and we use final hidden state
        _, (h_n, _) = self.lstm(x)
        out = self.fc(h_n[-1])  # Use last layer's hidden state
        return out


class LSTMRegressor(nn.Module):
    """LSTM for regression tasks."""

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = nn.LSTM(
            input_size,
            hidden_size,
            num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch, seq_len, features) - must be 3D
        _, (h_n, _) = self.lstm(x)
        out = self.fc(h_n[-1])
        return out.squeeze(-1)


def create_sequences(
    X: np.ndarray, y: np.ndarray | None, seq_len: int
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray]:
    """
    Create temporal sequences from flat feature matrix.

    For each sample at time t, creates a sequence of features from
    times [t-seq_len+1, ..., t]. Samples without enough history are dropped.

    Args:
        X: Feature matrix of shape (n_samples, n_features)
        y: Target array of shape (n_samples,) or None
        seq_len: Number of timesteps in each sequence

    Returns:
        X_seq: Sequences of shape (n_valid_samples, seq_len, n_features)
        y_seq: Targets for valid samples (aligned with last timestep)
        valid_indices: Original indices of valid samples
    """
    n_samples, n_features = X.shape

    # Need at least seq_len samples to form one sequence
    if n_samples < seq_len:
        # Return empty arrays with correct shape
        return (
            np.zeros((0, seq_len, n_features)),
            np.zeros(0) if y is not None else None,
            np.array([], dtype=int),
        )

    # Number of valid sequences (samples with enough history)
    n_valid = n_samples - seq_len + 1

    # Pre-allocate sequence array
    X_seq = np.zeros((n_valid, seq_len, n_features), dtype=np.float32)

    # Build sequences: for sample i, sequence includes [i, i+1, ..., i+seq_len-1]
    # The target is aligned with the LAST timestep of the sequence
    for i in range(n_valid):
        X_seq[i] = X[i : i + seq_len]

    # Targets align with the last timestep of each sequence
    # So target at index (seq_len-1) goes with first sequence, etc.
    valid_indices = np.arange(seq_len - 1, n_samples)
    y_seq = y[valid_indices] if y is not None else None

    return X_seq, y_seq, valid_indices


def train_lstm_classifier(
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_classes: int,
    seq_len: int = 20,
    hidden_size: int = 64,
    num_layers: int = 2,
    lr: float = 0.001,
    epochs: int = 100,
    batch_size: int = 32,
    device: str = "cuda",
) -> tuple[LSTMClassifier, StandardScaler, int]:
    """Train LSTM classifier with temporal sequences.

    Args:
        X_train: Training features (n_samples, n_features)
        y_train: Training labels
        n_classes: Number of classes
        seq_len: Sequence length for temporal modeling
        hidden_size: LSTM hidden size
        num_layers: Number of LSTM layers
        lr: Learning rate
        epochs: Training epochs
        batch_size: Batch size
        device: PyTorch device ("cuda" or "cpu")

    Returns:
        model: Trained LSTM classifier
        scaler: Fitted StandardScaler for features
        seq_len: Actual sequence length used (may be adjusted if not enough data)
    """
    # Standardize features BEFORE creating sequences
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)

    # Adjust seq_len if not enough data
    actual_seq_len = min(seq_len, len(X_scaled) // 2)  # At least 2 sequences
    actual_seq_len = max(actual_seq_len, 2)  # Minimum 2 timesteps

    # Create temporal sequences
    X_seq, y_seq, _ = create_sequences(X_scaled, y_train, actual_seq_len)

    if len(X_seq) < 10:
        # Not enough data for sequences, fall back to single-step
        actual_seq_len = 1
        X_seq = X_scaled.reshape(-1, 1, X_scaled.shape[1])
        y_seq = y_train

    # Convert to tensors
    X_tensor = torch.tensor(X_seq, dtype=torch.float32).to(device)
    y_tensor = torch.tensor(y_seq, dtype=torch.long).to(device)

    # Initialize model with correct input size (features per timestep)
    model = LSTMClassifier(
        input_size=X_scaled.shape[1],  # n_features
        hidden_size=hidden_size,
        num_layers=num_layers,
        n_classes=n_classes,
    ).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    # Training loop
    model.train()
    n_samples = len(X_tensor)
    for _ in range(epochs):
        # Shuffle data
        perm = torch.randperm(n_samples)
        for i in range(0, n_samples, batch_size):
            idx = perm[i : i + batch_size]
            X_batch = X_tensor[idx]
            y_batch = y_tensor[idx]

            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()

    model.eval()
    return model, scaler, actual_seq_len


def train_lstm_regressor(
    X_train: np.ndarray,
    y_train: np.ndarray,
    seq_len: int = 20,
    hidden_size: int = 64,
    num_layers: int = 2,
    lr: float = 0.001,
    epochs: int = 100,
    batch_size: int = 32,
    device: str = "cuda",
) -> tuple[LSTMRegressor, StandardScaler, int]:
    """Train LSTM regressor with temporal sequences.

    Args:
        X_train: Training features (n_samples, n_features)
        y_train: Training targets
        seq_len: Sequence length for temporal modeling
        hidden_size: LSTM hidden size
        num_layers: Number of LSTM layers
        lr: Learning rate
        epochs: Training epochs
        batch_size: Batch size
        device: PyTorch device ("cuda" or "cpu")

    Returns:
        model: Trained LSTM regressor
        scaler: Fitted StandardScaler for features
        seq_len: Actual sequence length used (may be adjusted if not enough data)
    """
    # Standardize features BEFORE creating sequences
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)

    # Adjust seq_len if not enough data
    actual_seq_len = min(seq_len, len(X_scaled) // 2)  # At least 2 sequences
    actual_seq_len = max(actual_seq_len, 2)  # Minimum 2 timesteps

    # Create temporal sequences
    X_seq, y_seq, _ = create_sequences(X_scaled, y_train, actual_seq_len)

    if len(X_seq) < 10:
        # Not enough data for sequences, fall back to single-step
        actual_seq_len = 1
        X_seq = X_scaled.reshape(-1, 1, X_scaled.shape[1])
        y_seq = y_train

    # Convert to tensors
    X_tensor = torch.tensor(X_seq, dtype=torch.float32).to(device)
    y_tensor = torch.tensor(y_seq.astype(np.float32), dtype=torch.float32).to(device)

    # Initialize model
    model = LSTMRegressor(
        input_size=X_scaled.shape[1],  # n_features
        hidden_size=hidden_size,
        num_layers=num_layers,
    ).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    model.train()
    n_samples = len(X_tensor)
    for _ in range(epochs):
        perm = torch.randperm(n_samples)
        for i in range(0, n_samples, batch_size):
            idx = perm[i : i + batch_size]
            X_batch = X_tensor[idx]
            y_batch = y_tensor[idx]

            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()

    model.eval()
    return model, scaler, actual_seq_len


# Exports
__all__ = [
    "LSTMClassifier",
    "LSTMRegressor",
    "create_sequences",
    "train_lstm_classifier",
    "train_lstm_regressor",
]
