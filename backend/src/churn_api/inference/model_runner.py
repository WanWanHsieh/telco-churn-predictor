"""推論介面與 Keras 實作（design.md 1.3、5.3）。

Service 只依賴 `ModelRunner` Protocol，測試時可注入假物件而不需要 TensorFlow。
"""

import threading
from typing import Any, Final, Protocol

import numpy as np
from numpy.typing import NDArray

CHUNK_SIZE: Final = 2048  # 批次推論每塊列數（design.md 5.3）


class ModelRunner(Protocol):
    """輸入 (n, 45) float32 前處理後矩陣，回傳 (n,) 的流失機率（0–1）。"""

    def predict_proba(self, features: NDArray[np.float32]) -> NDArray[np.float64]: ...


class KerasModelRunner:
    """以 `model(x, training=False)` 推論（不用 `model.predict`，避免每次建立 data adapter）。"""

    def __init__(self, model: Any, chunk_size: int = CHUNK_SIZE) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 需為正整數")
        self._model = model
        self._chunk_size = chunk_size
        self._lock = threading.Lock()  # 單一 worker 的 threadpool 下避免同時進入同一模型

    def predict_proba(self, features: NDArray[np.float32]) -> NDArray[np.float64]:
        matrix = np.ascontiguousarray(features, dtype=np.float32)
        if matrix.ndim != 2:
            raise ValueError(f"輸入需為二維矩陣，收到 {matrix.ndim} 維")
        outputs: list[NDArray[np.float64]] = []
        for start in range(0, len(matrix), self._chunk_size):
            chunk = matrix[start : start + self._chunk_size]
            with self._lock:
                result = self._model(chunk, training=False)
            outputs.append(np.asarray(result, dtype=np.float64).reshape(-1))
        if not outputs:
            return np.empty(0, dtype=np.float64)
        return np.concatenate(outputs)
