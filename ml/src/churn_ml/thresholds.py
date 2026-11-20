"""決策門檻選擇（design.md 4.4）。只使用驗證集。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

# 候選門檻 0.05–0.95，間隔 0.01
CANDIDATES: NDArray[np.float64] = np.round(np.arange(5, 96) / 100.0, 2)


@dataclass(frozen=True)
class ThresholdChoice:
    threshold: float
    recall: float
    precision: float
    f1: float
    target_met: bool
    warning: str | None  # 未達 Recall 目標時的說明（寫入 metrics.json.warnings）


def _scores(
    y: NDArray[np.int64], proba: NDArray[np.float64], threshold: float
) -> tuple[float, float, float]:
    predicted = proba >= threshold
    tp = float(np.sum(predicted & (y == 1)))
    fp = float(np.sum(predicted & (y == 0)))
    fn = float(np.sum(~predicted & (y == 1)))
    precision = tp / (tp + fp) if tp + fp > 0 else 0.0
    recall = tp / (tp + fn) if tp + fn > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
    return precision, recall, f1


def select_threshold(
    y_true: NDArray[np.int64], proba: NDArray[np.float64], target_recall: float
) -> ThresholdChoice:
    """在驗證集選門檻：Recall >= target_recall 條件下 F1 最大者；同分取較高門檻。

    沒有任何門檻達標時，選 Recall 最大者（再比 F1、較高門檻），並回傳警告文字。
    """
    scored = [(float(t), *_scores(y_true, proba, float(t))) for t in CANDIDATES]
    qualified = [s for s in scored if s[2] >= target_recall]
    if qualified:
        best = max(qualified, key=lambda s: (s[3], s[0]))
        return ThresholdChoice(best[0], best[2], best[1], best[3], True, None)
    best = max(scored, key=lambda s: (s[2], s[3], s[0]))
    warning = (
        f"驗證集上沒有任何門檻能達到目標 Recall {target_recall:.2f}，"
        f"改選 Recall 最大的門檻 {best[0]:.2f}（Recall {best[2]:.4f}）"
    )
    return ThresholdChoice(best[0], best[2], best[1], best[3], False, warning)
