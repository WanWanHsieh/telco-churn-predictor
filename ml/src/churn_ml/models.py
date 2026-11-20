"""模型定義與訓練（design.md 4.3）：Keras MLP（主模型）與邏輯迴歸（基準）。"""

from __future__ import annotations

from typing import Any

import keras
import numpy as np
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression

from churn_ml.reproducibility import set_global_seed

N_FEATURES = 45


def build_mlp(n_features: int = N_FEATURES) -> Any:
    """Input(45) → Dense(32) → Dropout → Dense(16) → Dropout → Dense(1, sigmoid)。

    隱藏層為 relu 並帶 L2=1e-4，Dropout 0.2；Adam(lr=1e-3)、binary_crossentropy。
    """
    l2 = keras.regularizers.L2(1e-4)
    model = keras.Sequential(
        [
            keras.Input(shape=(n_features,)),
            keras.layers.Dense(32, activation="relu", kernel_regularizer=l2),
            keras.layers.Dropout(0.2),
            keras.layers.Dense(16, activation="relu", kernel_regularizer=l2),
            keras.layers.Dropout(0.2),
            keras.layers.Dense(1, activation="sigmoid"),
        ]
    )
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-3),
        loss="binary_crossentropy",
        metrics=[keras.metrics.AUC(name="auc")],
    )
    return model


def build_logreg(seed: int, *, class_weight: str | None = None) -> LogisticRegression:
    """邏輯迴歸基準：C=1.0、lbfgs、max_iter=1000。"""
    return LogisticRegression(
        C=1.0, max_iter=1000, solver="lbfgs", random_state=seed, class_weight=class_weight
    )


def balanced_class_weight(y: NDArray[np.int64]) -> dict[int, float]:
    """與 sklearn `class_weight="balanced"` 相同公式：n / (2 * 各類別筆數)。"""
    n = len(y)
    return {label: n / (2.0 * float(np.sum(y == label))) for label in (0, 1)}


def train_mlp(
    x_train: NDArray[np.float32],
    y_train: NDArray[np.int64],
    x_val: NDArray[np.float32],
    y_val: NDArray[np.int64],
    *,
    seed: int,
    epochs: int,
    batch_size: int = 64,
    patience: int = 10,
    weighted: bool = False,
) -> tuple[Any, int]:
    """訓練 MLP，回傳（模型, 實際跑的 epoch 數）。

    訓練前重設種子，使結果與先前訓練過什麼無關。EarlyStopping 監看驗證集 AUC。
    """
    set_global_seed(seed)
    model = build_mlp(x_train.shape[1])
    stopper = keras.callbacks.EarlyStopping(
        monitor="val_auc", mode="max", patience=patience, restore_best_weights=True
    )
    history = model.fit(
        x_train,
        y_train,
        validation_data=(x_val, y_val),
        epochs=epochs,
        batch_size=batch_size,
        callbacks=[stopper],
        class_weight=balanced_class_weight(y_train) if weighted else None,
        verbose=0,
    )
    return model, len(history.history["loss"])


def predict_proba_mlp(model: Any, x: NDArray[np.float32]) -> NDArray[np.float64]:
    """流失機率（float64 一維陣列）。"""
    output = model(x, training=False)
    return np.asarray(output, dtype=np.float64).ravel()


def predict_proba_logreg(model: LogisticRegression, x: NDArray[np.float32]) -> NDArray[np.float64]:
    return np.asarray(model.predict_proba(x)[:, 1], dtype=np.float64)
