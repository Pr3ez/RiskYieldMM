"""Causal sequence embeddings for RPF binary classification.

This module is intentionally small and opt-in. It trains a lightweight 1D CNN
inside each walk-forward fold and appends the learned embedding to the
ElasticNet-selected tabular RPF panel before CatBoost.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


SEQUENCE_NONE = "none"
SEQUENCE_CAUSAL_CNN_V1 = "causal_cnn_v1"
SEQUENCE_EMBEDDING_MODES = (SEQUENCE_NONE, SEQUENCE_CAUSAL_CNN_V1)


@dataclass(frozen=True)
class SequenceEmbeddingConfig:
    mode: str = SEQUENCE_NONE
    sequence_length: int = 16
    embedding_dim: int = 8
    conv_channels: int = 16
    kernel_size: int = 3
    dropout: float = 0.10
    epochs: int = 3
    batch_size: int = 512
    learning_rate: float = 0.001
    max_train_rows: int = 12000
    device: str = "cpu"

    @property
    def enabled(self) -> bool:
        return self.mode == SEQUENCE_CAUSAL_CNN_V1


def append_causal_sequence_embeddings(
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_future: np.ndarray,
    config: SequenceEmbeddingConfig,
    X_sequence_train: np.ndarray | None = None,
    X_sequence_future: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Append CNN embeddings for train rows and a future split.

    The future split can be validation or prediction. Its sequence context is
    `[train rows][future rows]`; every anchor uses only rows at or before that
    anchor. Labels from the future split are never used.

    By default the CNN sees the same matrix as the tabular branch. When
    `X_sequence_train` and `X_sequence_future` are provided, the CNN is fit on
    that separate sequence panel and only its embeddings are appended to the
    tabular matrices consumed by CatBoost.
    """

    if not config.enabled:
        return X_train, X_future, sequence_diagnostics(config, enabled=False)
    sequence_train = X_train if X_sequence_train is None else X_sequence_train
    sequence_future = X_future if X_sequence_future is None else X_sequence_future
    validate_sequence_inputs(sequence_train, y_train, sequence_future, config)
    if sequence_train.shape[0] != X_train.shape[0] or sequence_future.shape[0] != X_future.shape[0]:
        raise ValueError("Sequence panel rows must align with tabular train/future rows")
    embedder = fit_causal_cnn_embedder(sequence_train, y_train, config=config)
    train_anchor_indexes = np.arange(sequence_train.shape[0], dtype=np.int64)
    full = np.vstack([sequence_train, sequence_future])
    future_anchor_indexes = np.arange(
        sequence_train.shape[0],
        sequence_train.shape[0] + sequence_future.shape[0],
        dtype=np.int64,
    )
    train_embeddings = embedder.transform(sequence_train, train_anchor_indexes)
    future_embeddings = embedder.transform(full, future_anchor_indexes)
    diagnostics = sequence_diagnostics(
        config,
        enabled=True,
        train_embedding_rows=int(train_embeddings.shape[0]),
        future_embedding_rows=int(future_embeddings.shape[0]),
        embedding_dim=int(train_embeddings.shape[1]),
        cnn_train_rows=int(embedder.train_rows),
        sequence_input_features=int(sequence_train.shape[1]),
    )
    return (
        np.hstack([X_train, train_embeddings]).astype("float32", copy=False),
        np.hstack([X_future, future_embeddings]).astype("float32", copy=False),
        diagnostics,
    )


def sequence_feature_names(config: SequenceEmbeddingConfig) -> tuple[str, ...]:
    if not config.enabled:
        return ()
    return tuple(f"rpf_seq_cnn_e{i:02d}" for i in range(int(config.embedding_dim)))


def validate_sequence_inputs(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_future: np.ndarray,
    config: SequenceEmbeddingConfig,
) -> None:
    if config.mode not in SEQUENCE_EMBEDDING_MODES:
        raise ValueError(f"Unsupported sequence embedding mode: {config.mode}")
    if int(config.sequence_length) <= 0:
        raise ValueError("sequence_length must be positive")
    if int(config.embedding_dim) <= 0:
        raise ValueError("embedding_dim must be positive")
    if int(config.conv_channels) <= 0:
        raise ValueError("conv_channels must be positive")
    if int(config.kernel_size) <= 0:
        raise ValueError("kernel_size must be positive")
    if X_train.ndim != 2 or X_future.ndim != 2:
        raise ValueError("Sequence embedding expects 2D train/future matrices")
    if X_train.shape[1] != X_future.shape[1]:
        raise ValueError("Train and future matrices must have the same feature count")
    if len(y_train) != X_train.shape[0]:
        raise ValueError("y_train length must match X_train rows")
    if X_train.shape[0] == 0:
        raise ValueError("Cannot train sequence embedder with zero train rows")
    if len(np.unique(y_train)) < 2:
        raise ValueError("Sequence embedder requires two train classes")


class CausalCNNEmbedder:
    def __init__(self, model: Any, config: SequenceEmbeddingConfig, train_rows: int):
        self.model = model
        self.config = config
        self.train_rows = int(train_rows)

    def transform(self, full_matrix: np.ndarray, anchor_indexes: np.ndarray) -> np.ndarray:
        import torch

        self.model.eval()
        outputs: list[np.ndarray] = []
        batch_size = max(1, int(self.config.batch_size))
        with torch.no_grad():
            for start in range(0, len(anchor_indexes), batch_size):
                batch_indexes = anchor_indexes[start : start + batch_size]
                seq = causal_sequence_tensor(full_matrix, batch_indexes, int(self.config.sequence_length))
                tensor = torch.from_numpy(seq).to(self.config.device)
                embedding = self.model.embedding(tensor).detach().cpu().numpy().astype("float32")
                outputs.append(embedding)
        if not outputs:
            return np.empty((0, int(self.config.embedding_dim)), dtype="float32")
        return np.vstack(outputs)


def fit_causal_cnn_embedder(
    X_train: np.ndarray,
    y_train: np.ndarray,
    *,
    config: SequenceEmbeddingConfig,
) -> CausalCNNEmbedder:
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except Exception as exc:  # pragma: no cover - depends on active env
        raise RuntimeError("PyTorch is required for causal_cnn_v1 sequence embeddings") from exc

    torch.manual_seed(42)
    train_rows = min(int(config.max_train_rows), int(X_train.shape[0])) if int(config.max_train_rows) > 0 else int(X_train.shape[0])
    anchor_indexes = evenly_spaced_indexes(X_train.shape[0], train_rows)
    seq = causal_sequence_tensor(X_train, anchor_indexes, int(config.sequence_length))
    y = np.asarray(y_train, dtype=np.float32)[anchor_indexes]
    dataset = TensorDataset(torch.from_numpy(seq), torch.from_numpy(y.reshape(-1, 1)))
    loader = DataLoader(dataset, batch_size=max(1, int(config.batch_size)), shuffle=True)
    model = _TinyCausalCNN(
        input_features=int(X_train.shape[1]),
        conv_channels=int(config.conv_channels),
        kernel_size=int(config.kernel_size),
        embedding_dim=int(config.embedding_dim),
        dropout=float(config.dropout),
    ).to(config.device)
    positives = float(np.sum(y == 1.0))
    negatives = float(np.sum(y == 0.0))
    pos_weight = torch.tensor([max(1.0, negatives / positives)], device=config.device) if positives > 0 else torch.tensor([1.0], device=config.device)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(config.learning_rate))
    model.train()
    for _ in range(max(1, int(config.epochs))):
        for xb, yb in loader:
            xb = xb.to(config.device)
            yb = yb.to(config.device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(xb)
            loss = loss_fn(logits, yb)
            loss.backward()
            optimizer.step()
    return CausalCNNEmbedder(model=model, config=config, train_rows=int(len(anchor_indexes)))


def causal_sequence_tensor(full_matrix: np.ndarray, anchor_indexes: np.ndarray, sequence_length: int) -> np.ndarray:
    X = np.asarray(full_matrix, dtype=np.float32)
    anchors = np.asarray(anchor_indexes, dtype=np.int64)
    seq_len = int(sequence_length)
    out = np.zeros((len(anchors), X.shape[1], seq_len), dtype=np.float32)
    for row_idx, anchor in enumerate(anchors):
        start = max(0, int(anchor) - seq_len + 1)
        window = X[start : int(anchor) + 1]
        out[row_idx, :, -window.shape[0] :] = window.T
    return out


def evenly_spaced_indexes(row_count: int, max_rows: int) -> np.ndarray:
    if int(max_rows) <= 0 or int(max_rows) >= int(row_count):
        return np.arange(int(row_count), dtype=np.int64)
    return np.unique(np.linspace(0, int(row_count) - 1, int(max_rows), dtype=np.int64))


def sequence_diagnostics(
    config: SequenceEmbeddingConfig,
    *,
    enabled: bool,
    train_embedding_rows: int | None = None,
    future_embedding_rows: int | None = None,
    embedding_dim: int | None = None,
    cnn_train_rows: int | None = None,
    sequence_input_features: int | None = None,
) -> dict[str, Any]:
    return {
        "sequence_embedding_mode": config.mode,
        "sequence_embedding_enabled": bool(enabled),
        "sequence_length": int(config.sequence_length),
        "sequence_embedding_dim": int(config.embedding_dim) if enabled else 0,
        "sequence_conv_channels": int(config.conv_channels),
        "sequence_kernel_size": int(config.kernel_size),
        "sequence_dropout": float(config.dropout),
        "sequence_epochs": int(config.epochs),
        "sequence_batch_size": int(config.batch_size),
        "sequence_learning_rate": float(config.learning_rate),
        "sequence_max_train_rows": int(config.max_train_rows),
        "sequence_input_features": sequence_input_features,
        "sequence_cnn_train_rows": cnn_train_rows,
        "sequence_train_embedding_rows": train_embedding_rows,
        "sequence_future_embedding_rows": future_embedding_rows,
        "sequence_actual_embedding_dim": embedding_dim,
    }


class _TinyCausalCNN:
    def __new__(
        cls,
        *,
        input_features: int,
        conv_channels: int,
        kernel_size: int,
        embedding_dim: int,
        dropout: float,
    ) -> Any:
        import torch
        from torch import nn

        class Model(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                padding = max(0, int(kernel_size) - 1)
                self.conv = nn.Conv1d(input_features, conv_channels, kernel_size=kernel_size, padding=padding)
                self.activation = nn.ReLU()
                self.pool = nn.AdaptiveAvgPool1d(1)
                self.dropout = nn.Dropout(float(dropout))
                self.proj = nn.Linear(conv_channels, embedding_dim)
                self.head = nn.Linear(embedding_dim, 1)

            def embedding(self, x: Any) -> Any:
                z = self.conv(x)
                if z.shape[-1] > x.shape[-1]:
                    z = z[..., -x.shape[-1] :]
                z = self.activation(z)
                z = self.pool(z).squeeze(-1)
                z = self.dropout(z)
                return self.activation(self.proj(z))

            def forward(self, x: Any) -> Any:
                return self.head(self.embedding(x))

        torch.manual_seed(42)
        return Model()
