"""Telco churn 離線訓練管線。"""

import os

# 必須在任何 tensorflow／keras import 之前設定（子模組 import 前會先執行本檔）
os.environ.setdefault("KERAS_BACKEND", "tensorflow")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

__version__ = "0.1.0"
