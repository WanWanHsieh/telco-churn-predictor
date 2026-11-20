"""評估：五指標、混淆矩陣、ROC 降採樣，以及 metrics.json 結構檢查（design.md 6.5.4）。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import roc_auc_score, roc_curve

MODEL_KEYS = ("logistic_regression", "keras_mlp")
METRIC_NAMES = ("roc_auc", "precision", "recall", "f1", "accuracy")
ROC_POINTS = 101


@dataclass(frozen=True)
class Evaluation:
    """在指定門檻下的測試結果（未四捨五入）。"""

    roc_auc: float
    precision: float
    recall: float
    f1: float
    accuracy: float
    tn: int
    fp: int
    fn: int
    tp: int

    def metrics_dict(self) -> dict[str, float]:
        """五指標，四捨五入到 4 位小數（metrics.json 格式）。"""
        return {name: round(float(getattr(self, name)), 4) for name in METRIC_NAMES}

    def confusion_dict(self) -> dict[str, int]:
        return {"tn": self.tn, "fp": self.fp, "fn": self.fn, "tp": self.tp}


def evaluate(y_true: NDArray[np.int64], proba: NDArray[np.float64], threshold: float) -> Evaluation:
    """以 `proba >= threshold` 判為流失，計算五指標與混淆矩陣。分母為 0 時該指標為 0。"""
    predicted = proba >= threshold
    positive = y_true == 1
    tp = int(np.sum(predicted & positive))
    fp = int(np.sum(predicted & ~positive))
    fn = int(np.sum(~predicted & positive))
    tn = int(np.sum(~predicted & ~positive))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return Evaluation(
        roc_auc=float(roc_auc_score(y_true, proba)),
        precision=precision,
        recall=recall,
        f1=f1,
        accuracy=(tp + tn) / len(y_true),
        tn=tn,
        fp=fp,
        fn=fn,
        tp=tp,
    )


def roc_curve_downsampled(
    y_true: NDArray[np.int64], proba: NDArray[np.float64]
) -> dict[str, list[float]]:
    """ROC 曲線降採樣為 FPR 0～1 間隔 0.01 共 101 點，含 (0,0) 與 (1,1)。"""
    fpr, tpr, _ = roc_curve(y_true, proba)
    grid = np.round(np.linspace(0.0, 1.0, ROC_POINTS), 2)
    sampled = np.interp(grid, fpr, tpr)
    sampled[0] = 0.0
    sampled[-1] = 1.0
    return {
        "fpr": [float(v) for v in grid],
        "tpr": [round(float(v), 4) for v in sampled],
    }


# ---------------------------------------------------------------- 結構檢查
_TOP_KEYS = {
    "primary_model": str,
    "model_version": str,
    "trained_at": str,
    "random_seed": int,
    "imbalance_strategy": str,
    "target_recall": float,
    "dataset": dict,
    "models": list,
    "decision_threshold": float,
    "imbalance_experiment": list,
    "warnings": list,
}
_DATASET_KEYS = (
    "train_size",
    "validation_size",
    "test_size",
    "test_churn_rate",
    "majority_class_accuracy",
)
_EXPERIMENT_KEYS = (
    "model",
    "strategy",
    "threshold_rule",
    "threshold",
    "recall",
    "precision",
    "roc_auc",
)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def check_metrics_structure(data: Mapping[str, Any]) -> list[str]:
    """檢查 metrics.json 是否符合 design.md 6.5.4；回傳所有問題（空清單代表通過）。"""
    problems: list[str] = []
    for key, expected in _TOP_KEYS.items():
        if key not in data:
            problems.append(f"缺少欄位 {key}")
        elif expected is float and not _is_number(data[key]):
            problems.append(f"{key} 需為數字")
        elif expected is not float and (
            not isinstance(data[key], expected) or isinstance(data[key], bool)
        ):
            problems.append(f"{key} 型別錯誤")
    if problems:
        return problems

    if data["primary_model"] != "keras_mlp":
        problems.append("primary_model 需為 keras_mlp")
    if data["imbalance_strategy"] not in ("threshold_tuning", "class_weight"):
        problems.append("imbalance_strategy 值不合法")
    dataset = data["dataset"]
    for key in _DATASET_KEYS:
        if key not in dataset or not _is_number(dataset[key]):
            problems.append(f"dataset.{key} 缺少或不是數字")

    models = data["models"]
    if [m.get("key") for m in models if isinstance(m, dict)] != list(MODEL_KEYS):
        problems.append("models 需恰 2 筆且順序為 logistic_regression、keras_mlp")
    else:
        for model in models:
            problems.extend(_check_model(model))
        if data["decision_threshold"] != models[1]["decision_threshold"]:
            problems.append("decision_threshold 需等於 keras_mlp 的 decision_threshold")

    for i, row in enumerate(data["imbalance_experiment"]):
        missing = [k for k in _EXPERIMENT_KEYS if not isinstance(row, dict) or k not in row]
        if missing:
            problems.append(f"imbalance_experiment[{i}] 缺少 {'、'.join(missing)}")
        elif row["strategy"] not in ("none", "class_weight") or row["threshold_rule"] not in (
            "default_0.5",
            "tuned",
        ):
            problems.append(f"imbalance_experiment[{i}] 的 strategy 或 threshold_rule 不合法")
    if not data["imbalance_experiment"]:
        problems.append("imbalance_experiment 不可為空")
    if not all(isinstance(w, str) for w in data["warnings"]):
        problems.append("warnings 需為字串陣列")
    return problems


def _check_model(model: Mapping[str, Any]) -> list[str]:
    key = model.get("key")
    problems: list[str] = []
    for field in ("display_name", "decision_threshold", "metrics", "confusion_matrix", "roc_curve"):
        if field not in model:
            problems.append(f"{key}: 缺少 {field}")
    if problems:
        return problems
    if sorted(model["metrics"]) != sorted(METRIC_NAMES) or not all(
        _is_number(v) and 0.0 <= v <= 1.0 for v in model["metrics"].values()
    ):
        problems.append(f"{key}: metrics 需含五指標且為 0–1 數字")
    matrix = model["confusion_matrix"]
    if sorted(matrix) != ["fn", "fp", "tn", "tp"] or not all(
        isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in matrix.values()
    ):
        problems.append(f"{key}: confusion_matrix 需為 tn/fp/fn/tp 非負整數")
    roc = model["roc_curve"]
    fpr, tpr = roc.get("fpr"), roc.get("tpr")
    if not (isinstance(fpr, list) and isinstance(tpr, list) and len(fpr) == len(tpr) == ROC_POINTS):
        problems.append(f"{key}: roc_curve 的 fpr／tpr 需為等長 {ROC_POINTS} 點")
    elif (fpr[0], tpr[0], fpr[-1], tpr[-1]) != (0.0, 0.0, 1.0, 1.0):
        problems.append(f"{key}: roc_curve 需含 (0,0) 與 (1,1)")
    return problems
