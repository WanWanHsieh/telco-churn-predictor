"""Integrated Gradients 解釋器（design.md 3.3、ADR-0005）。

- 輸入空間：前處理後 45 維向量（float32）；基準點為訓練子集的平均向量（explainer.json）。
- 預設輸出空間為模型 sigmoid 後的機率，因此歸因單位是「機率」。
- 積分：`alphas = linspace(0, 1, m+1)`，梯形法，一次以 (m+1, 45) 的 batch 計算梯度。
- 以 `tf.function(input_signature=...)` 固定形狀；建構時暖機一次，避免第一個請求才追蹤。
- 完整性：Σ attribution ≈ p(x) − p(baseline)。

`Explainer` Protocol 讓 service 不需要 TensorFlow 即可測試。
"""

import threading
from collections.abc import Sequence
from typing import Any, Literal, Protocol

import numpy as np
from numpy.typing import NDArray


class Explainer(Protocol):
    """對單一前處理後向量計算 45 維歸因。"""

    @property
    def baseline_probability(self) -> float: ...

    def attribute(self, features: NDArray[np.float32]) -> NDArray[np.float64]: ...


class IntegratedGradientsExplainer:
    """以 `tf.GradientTape` 實作的 Integrated Gradients。

    `output="logit"` 只供測試驗證（無隱藏層模型在 logit 空間的解析解 w·(x−b)）；正式使用機率。
    """

    def __init__(
        self,
        model: Any,
        baseline: Sequence[float] | NDArray[np.floating[Any]],
        baseline_probability: float,
        steps: int = 64,
        output: Literal["probability", "logit"] = "probability",
    ) -> None:
        import tensorflow as tf  # 延遲匯入；沒有推論需求的程式不必載入 TensorFlow

        if steps <= 0:
            raise ValueError("steps 需為正整數")
        base = np.asarray(baseline, dtype=np.float32).reshape(-1)
        self._baseline_probability = float(baseline_probability)
        self._n_features = int(base.shape[0])
        self._lock = threading.Lock()

        baseline_tensor = tf.constant(base)
        alphas = tf.reshape(tf.linspace(0.0, 1.0, steps + 1), (-1, 1))
        use_logit = output == "logit"

        @tf.function(input_signature=[tf.TensorSpec([self._n_features], tf.float32)])  # type: ignore[untyped-decorator]
        def integrate(x: Any) -> tuple[Any, Any, Any]:
            delta = x - baseline_tensor
            path = baseline_tensor[None, :] + alphas * delta[None, :]  # (m+1, n)
            with tf.GradientTape() as tape:
                tape.watch(path)
                probs = tf.reshape(model(path, training=False), (-1,))
                target = tf.math.log(probs) - tf.math.log1p(-probs) if use_logit else probs
            grads = tape.gradient(target, path)
            # 梯形法：兩端權重 1/2
            average = (tf.reduce_sum(grads, axis=0) - 0.5 * (grads[0] + grads[-1])) / steps
            return delta * average, probs[0], probs[-1]

        self._integrate = integrate

    @property
    def baseline_probability(self) -> float:
        return self._baseline_probability

    @property
    def n_features(self) -> int:
        return self._n_features

    def attribute_with_endpoints(
        self, features: NDArray[np.float32]
    ) -> tuple[NDArray[np.float64], float, float]:
        """回傳（歸因, p(基準), p(x)）；端點機率供完整性檢查使用。"""
        vector = np.asarray(features, dtype=np.float32).reshape(-1)
        if vector.shape[0] != self._n_features:
            raise ValueError(f"輸入維度需為 {self._n_features}，收到 {vector.shape[0]}")
        with self._lock:
            attribution, p_base, p_x = self._integrate(vector)
        return (
            np.asarray(attribution, dtype=np.float64),
            float(p_base),
            float(p_x),
        )

    def attribute(self, features: NDArray[np.float32]) -> NDArray[np.float64]:
        return self.attribute_with_endpoints(features)[0]

    def warm_up(self, features: NDArray[np.float32]) -> None:
        """用一筆範例向量先跑一次，完成 graph 追蹤。"""
        self.attribute(features)
