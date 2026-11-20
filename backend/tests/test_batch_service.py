"""BatchService：向量化估算與前處理、分塊推論、摘要、input 回傳（注入假 runner）。"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from churn_api.schemas.common import ModelInfo, RiskThresholds
from churn_api.services.batch_service import BatchService
from churn_api.services.csv_parser import parse_batch_csv
from churn_core.preprocessing import Preprocessor

INFO = ModelInfo(name="keras_mlp", display_name="Keras", version="v1", trained_at="2026-11-20")
THRESHOLDS = RiskThresholds(medium=0.30, high=0.60)


@pytest.fixture
def preprocessor(artifact_dir: Path) -> Preprocessor:
    return Preprocessor.from_json((artifact_dir / "preprocessor.json").read_text("utf-8"))


def _batch(content: bytes) -> Any:
    return parse_batch_csv("x.csv", content, max_file_bytes=10**7, max_rows=10_000)


class ScriptedRunner:
    """依呼叫順序回傳指定機率，用來驗證摘要與分級。"""

    def __init__(self, probabilities: list[float]) -> None:
        self._values = np.asarray(probabilities, dtype=np.float64)

    def predict_proba(self, features: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        assert len(features) == len(self._values)
        return self._values


def test_results_in_file_order_with_summary_and_levels(
    preprocessor: Preprocessor,
    record: Callable[..., dict[str, Any]],
    make_csv: Callable[..., bytes],
) -> None:
    probabilities = [0.29, 0.30, 0.59, 0.60, 0.2995, 0.05, 0.99]
    rows = [{**record(tenure=i + 1), "customerID": f"C{i}"} for i in range(len(probabilities))]
    batch = _batch(make_csv(rows))
    response = BatchService(ScriptedRunner(probabilities), preprocessor, INFO, THRESHOLDS).predict(
        batch
    )

    assert [r.row for r in response.results] == list(range(2, 2 + len(rows)))  # 原始順序
    assert [r.customer_id for r in response.results] == [f"C{i}" for i in range(len(rows))]
    assert [r.risk_level for r in response.results] == [
        "low",
        "medium",
        "medium",
        "high",
        "medium",  # 0.2995 → 0.300 → medium
        "low",
        "high",
    ]
    assert [r.probability for r in response.results] == [0.29, 0.3, 0.59, 0.6, 0.3, 0.05, 0.99]
    assert response.summary.model_dump() == {
        "total": 7,
        "high": 2,
        "medium": 3,
        "low": 2,
        "estimated_total_charges": 7,  # 範例 record 省略 TotalCharges
    }
    assert response.summary.high + response.summary.medium + response.summary.low == 7
    assert response.model == INFO
    assert response.risk_thresholds == THRESHOLDS
    assert response.has_customer_id is True
    assert response.ignored_columns == []


def test_estimated_flags_and_input_echo(
    preprocessor: Preprocessor,
    record: Callable[..., dict[str, Any]],
    make_csv: Callable[..., bytes],
) -> None:
    rows = [
        record(tenure=10, MonthlyCharges=50.0, TotalCharges=None),
        record(tenure=10, MonthlyCharges=50.0, TotalCharges=500),
        record(tenure=3, MonthlyCharges=20.0, TotalCharges=61.5),
    ]
    batch = _batch(make_csv(rows))
    response = BatchService(
        ScriptedRunner([0.1, 0.1, 0.1]), preprocessor, INFO, THRESHOLDS
    ).predict(batch)
    assert [r.total_charges_estimated for r in response.results] == [True, False, False]
    assert response.summary.estimated_total_charges == 1
    # input：TotalCharges 為原始值（空白為 null），其餘為正規化後型別
    dumped = [r.input.model_dump() for r in response.results]
    assert [d["TotalCharges"] for d in dumped] == [None, 500.0, 61.5]
    assert dumped[0]["tenure"] == 10
    assert isinstance(dumped[0]["SeniorCitizen"], int)
    assert len(dumped[0]) == 19
    assert [r.customer_id for r in response.results] == [None, None, None]  # 欄在但空白


def test_estimated_and_explicit_rows_get_same_vector(
    preprocessor: Preprocessor,
    record: Callable[..., dict[str, Any]],
    make_csv: Callable[..., bytes],
    fake_runner: Callable[..., Any],
) -> None:
    """AC-6.13：省略 TotalCharges 的列與填入同一估算值的列，進入模型的向量完全相同。"""
    rows = [
        record(tenure=10, MonthlyCharges=50.0),
        record(tenure=10, MonthlyCharges=50.0, TotalCharges=500),
    ]
    runner = fake_runner()
    response = BatchService(runner, preprocessor, INFO, THRESHOLDS).predict(_batch(make_csv(rows)))
    matrix = runner.calls[0]
    assert np.array_equal(matrix[0], matrix[1])
    assert response.results[0].probability == response.results[1].probability


def test_repeated_prediction_is_identical(
    preprocessor: Preprocessor,
    record: Callable[..., dict[str, Any]],
    make_csv: Callable[..., bytes],
    fake_runner: Callable[..., Any],
) -> None:
    """AC-6.12：同一份檔案處理兩次，結果完全相同。"""
    data = make_csv([record(tenure=t, MonthlyCharges=20.0 + t) for t in range(1, 40)])
    service = BatchService(fake_runner(), preprocessor, INFO, THRESHOLDS)
    assert service.predict(_batch(data)) == service.predict(_batch(data))


def test_single_runner_call_for_whole_batch(
    preprocessor: Preprocessor,
    record: Callable[..., dict[str, Any]],
    make_csv: Callable[..., bytes],
    fake_runner: Callable[..., Any],
) -> None:
    """向量化：整批只呼叫一次 runner（分塊由 runner 內部處理）。"""
    runner = fake_runner()
    BatchService(runner, preprocessor, INFO, THRESHOLDS).predict(_batch(make_csv([record()] * 50)))
    assert len(runner.calls) == 1
    assert runner.calls[0].shape == (50, 45)
