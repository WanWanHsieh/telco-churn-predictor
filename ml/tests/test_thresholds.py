import numpy as np

from churn_ml.thresholds import CANDIDATES, select_threshold


def test_candidates_are_0_05_to_0_95_step_0_01() -> None:
    assert CANDIDATES[0] == 0.05
    assert CANDIDATES[-1] == 0.95
    assert len(CANDIDATES) == 91
    assert np.allclose(np.diff(CANDIDATES), 0.01)


def test_picks_max_f1_among_thresholds_meeting_target_recall() -> None:
    # 流失者機率 0.9/0.8/0.4/0.3；非流失者 0.7/0.2/0.1/0.05
    y = np.array([1, 1, 1, 1, 0, 0, 0, 0], dtype=np.int64)
    p = np.array([0.9, 0.8, 0.4, 0.3, 0.7, 0.2, 0.1, 0.05])
    choice = select_threshold(y, p, target_recall=0.75)

    # Recall >= 0.75 需抓到 3 個以上，候選為門檻 <= 0.4。
    # 門檻 0.3：抓到 4 個流失者、1 個誤判 → precision 0.8、recall 1.0、F1 0.8889（最大）
    # 門檻 0.4：recall 0.75、precision 0.75、F1 0.75
    assert choice.target_met is True
    assert choice.warning is None
    assert choice.threshold == 0.3
    assert choice.recall == 1.0
    assert round(choice.f1, 4) == 0.8889


def test_ties_choose_higher_threshold() -> None:
    y = np.array([1, 1, 0, 0], dtype=np.int64)
    p = np.array([0.9, 0.9, 0.1, 0.1])
    choice = select_threshold(y, p, target_recall=0.75)
    assert choice.threshold == 0.9  # 0.11–0.9 全部 F1=1，取最高
    assert choice.f1 == 1.0


def test_no_threshold_meets_target_picks_max_recall_with_warning() -> None:
    # 所有流失者的機率都低於 0.05：任何候選門檻 Recall 皆為 0 → 無法達標
    y = np.array([1, 1, 0, 0], dtype=np.int64)
    p = np.array([0.01, 0.02, 0.5, 0.6])
    choice = select_threshold(y, p, target_recall=0.75)
    assert choice.target_met is False
    assert choice.recall == 0.0
    assert choice.warning is not None
    assert "0.75" in choice.warning


def test_unreachable_target_falls_back_to_largest_recall() -> None:
    # 流失者 0.04（任何候選門檻都抓不到）與 0.9：最大 Recall 為 0.5（門檻 <= 0.9）
    y = np.array([1, 1, 0, 0], dtype=np.int64)
    p = np.array([0.04, 0.9, 0.5, 0.2])
    choice = select_threshold(y, p, target_recall=0.75)
    assert choice.target_met is False
    assert choice.recall == 0.5
    assert choice.threshold == 0.9  # Recall 同為 0.5 時取 F1 較高者（誤判最少）
    assert choice.warning is not None


def test_zero_division_is_safe() -> None:
    y = np.zeros(4, dtype=np.int64)  # 沒有流失者
    p = np.array([0.9, 0.8, 0.1, 0.1])
    choice = select_threshold(y, p, target_recall=0.75)
    assert choice.recall == 0.0
    assert choice.precision == 0.0
    assert choice.target_met is False
