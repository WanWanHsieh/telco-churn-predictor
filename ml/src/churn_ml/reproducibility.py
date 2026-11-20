"""亂數種子與 TensorFlow 決定性（design.md 4.2 步驟 1）。"""

from __future__ import annotations

import os
import random

import keras
import numpy as np
import tensorflow as tf


def set_global_seed(seed: int) -> None:
    """設定所有亂數來源並開啟 TF 決定性運算。

    每次訓練 Keras 前都應呼叫，使每個模型的結果與訓練順序無關、可獨立重現。
    `PYTHONHASHSEED` 只對之後啟動的子行程生效，這裡照規格仍設定。
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    keras.utils.set_random_seed(seed)
    tf.config.experimental.enable_op_determinism()
