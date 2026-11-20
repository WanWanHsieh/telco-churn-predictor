import copy
from typing import Any

import numpy as np
import pytest

from churn_ml.evaluate import (
    ROC_POINTS,
    check_metrics_structure,
    evaluate,
    roc_curve_downsampled,
)
from churn_ml.pipeline import TrainingResult


def test_evaluate_known_values() -> None:
    y = np.array([1, 1, 1, 0, 0, 0, 0, 0], dtype=np.int64)
    p = np.array([0.9, 0.6, 0.2, 0.7, 0.4, 0.3, 0.1, 0.05])
    result = evaluate(y, p, threshold=0.5)

    assert (result.tp, result.fn, result.fp, result.tn) == (2, 1, 1, 4)
    assert result.precision == pytest.approx(2 / 3)
    assert result.recall == pytest.approx(2 / 3)
    assert result.f1 == pytest.approx(2 / 3)
    assert result.accuracy == pytest.approx(6 / 8)
    assert result.roc_auc == pytest.approx(11 / 15)  # 15 對中 11 對排序正確
    assert result.confusion_dict() == {"tn": 4, "fp": 1, "fn": 1, "tp": 2}
    assert result.metrics_dict()["precision"] == 0.6667  # 4 位小數


def test_evaluate_no_predicted_positive_gives_zero_precision() -> None:
    y = np.array([1, 0, 1, 0], dtype=np.int64)
    result = evaluate(y, np.array([0.1, 0.2, 0.3, 0.4]), threshold=0.9)
    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.f1 == 0.0


def test_roc_curve_is_downsampled_to_101_points() -> None:
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 300).astype(np.int64)
    p = np.clip(y * 0.3 + rng.random(300) * 0.7, 0, 1)
    roc = roc_curve_downsampled(y, p)

    assert len(roc["fpr"]) == len(roc["tpr"]) == ROC_POINTS == 101
    assert roc["fpr"][:3] == [0.0, 0.01, 0.02]
    assert (roc["fpr"][0], roc["tpr"][0]) == (0.0, 0.0)
    assert (roc["fpr"][-1], roc["tpr"][-1]) == (1.0, 1.0)
    assert all(a <= b for a, b in zip(roc["tpr"], roc["tpr"][1:], strict=False))  # 單調不減


def test_real_pipeline_metrics_pass_structure_check(trained_run: TrainingResult) -> None:  # AC-4.5
    assert check_metrics_structure(trained_run.metrics) == []
    assert len(trained_run.metrics["imbalance_experiment"]) == 8  # 2 模型 × 2 策略 × 2 門檻規則


def _good(trained_run: TrainingResult) -> dict[str, Any]:
    return copy.deepcopy(trained_run.metrics)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("imbalance_experiment"),
        lambda d: d.update(primary_model="logistic_regression"),
        lambda d: d.update(imbalance_strategy="other"),
        lambda d: d["models"].reverse(),
        lambda d: d["models"].pop(),
        lambda d: d["models"][1]["roc_curve"]["fpr"].pop(),
        lambda d: d["models"][1]["roc_curve"]["tpr"].__setitem__(0, 0.5),
        lambda d: d["models"][1]["metrics"].pop("f1"),
        lambda d: d["models"][1]["metrics"].update(recall=1.5),
        lambda d: d["models"][1]["confusion_matrix"].update(tp=-1),
        lambda d: d["models"][1]["confusion_matrix"].update(tp=1.5),
        lambda d: d.update(decision_threshold=0.99),
        lambda d: d["dataset"].pop("test_churn_rate"),
        lambda d: d["imbalance_experiment"][0].pop("recall"),
        lambda d: d["imbalance_experiment"][0].update(strategy="weird"),
        lambda d: d.update(imbalance_experiment=[]),
        lambda d: d.update(warnings=[1]),
        lambda d: d.update(random_seed="42"),
        lambda d: d.update(target_recall="0.75"),
    ],
)
def test_structure_check_detects_problems(trained_run: TrainingResult, mutate) -> None:  # type: ignore[no-untyped-def]
    data = _good(trained_run)
    mutate(data)
    assert check_metrics_structure(data) != []
