"""PredictionService：估算→前處理→預測→分級→因素聚合排序→中文 label（注入假 runner／explainer）。"""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from churn_api.errors import AppError, ErrorCode
from churn_api.schemas.common import ModelInfo, RiskThresholds
from churn_api.schemas.prediction import CustomerFeatures
from churn_api.services.prediction_service import PredictionService, aggregate_factors
from churn_core.preprocessing import N_FEATURES, Preprocessor
from churn_core.schema import FEATURES

INFO = ModelInfo(
    name="keras_mlp",
    display_name="Keras 神經網路",
    version="v-test",
    trained_at="2026-11-20T00:00:00Z",
)
THRESHOLDS = RiskThresholds(medium=0.30, high=0.60)
INTERNAL_NAME_PATTERN = re.compile(r"[A-Za-z_]+=|Month-to-month|Fiber optic|No internet service")


@pytest.fixture
def preprocessor(artifact_dir: Path) -> Preprocessor:
    return Preprocessor.from_json((artifact_dir / "preprocessor.json").read_text("utf-8"))


@pytest.fixture
def make_service(
    preprocessor: Preprocessor, fake_explainer: Callable[..., Any]
) -> Callable[..., PredictionService]:
    def factory(runner: Any, attribution: np.ndarray[Any, Any]) -> PredictionService:
        return PredictionService(
            runner, fake_explainer(attribution, 0.2465), preprocessor, INFO, THRESHOLDS
        )

    return factory


def _attribution_for(preprocessor: Preprocessor, impacts: dict[str, float]) -> np.ndarray[Any, Any]:
    """把「每個欄位的總影響」平均分給該欄位的 one-hot 維度。"""
    vector = np.zeros(N_FEATURES)
    for feature, total in impacts.items():
        indices = preprocessor.feature_groups[feature]
        vector[indices] = total / len(indices)
    return vector


@pytest.fixture
def features(record: Callable[..., dict[str, Any]]) -> CustomerFeatures:
    return CustomerFeatures.model_validate(record())


def test_response_fields_and_rounding(
    make_service: Callable[..., PredictionService],
    fake_runner: Callable[..., Any],
    preprocessor: Preprocessor,
    features: CustomerFeatures,
) -> None:
    attribution = _attribution_for(preprocessor, {"Contract": 0.1834, "tenure": -0.05})
    service = make_service(fake_runner(fixed=0.2995), attribution)
    response = service.predict(features)
    assert response.probability == 0.3  # half-up
    assert response.risk_level == "medium"  # 四捨五入後 0.300 → medium
    assert response.risk_thresholds == THRESHOLDS
    assert response.model == INFO
    assert response.explanation.method == "integrated_gradients"
    assert response.explanation.baseline_probability == 0.247  # 0.2465 half-up 到 3 位
    assert response.total_charges.value == 100.0
    assert response.total_charges.is_estimated is True


def test_top_factors_five_sorted_by_abs_with_direction_and_labels(
    make_service: Callable[..., PredictionService],
    fake_runner: Callable[..., Any],
    preprocessor: Preprocessor,
    features: CustomerFeatures,
) -> None:
    impacts = {
        "Contract": 0.2,
        "tenure": -0.15,
        "InternetService": 0.1,
        "PaymentMethod": -0.08,
        "TechSupport": 0.05,
        "gender": 0.001,
        "Partner": -0.002,
    }
    service = make_service(fake_runner(fixed=0.7), _attribution_for(preprocessor, impacts))
    factors = service.predict(features).top_factors

    assert [f.feature for f in factors] == [
        "Contract",
        "tenure",
        "InternetService",
        "PaymentMethod",
        "TechSupport",
    ]
    assert [f.direction for f in factors] == [
        "increase",
        "decrease",
        "increase",
        "decrease",
        "increase",
    ]
    assert [f.impact for f in factors] == [0.2, -0.15, 0.1, -0.08, 0.05]
    assert factors[0].label == "合約類型：月繳"
    assert factors[1].label == "在網月數：1 個月"
    assert factors[2].label == "網路服務：光纖"
    for factor in factors:
        assert not INTERNAL_NAME_PATTERN.search(factor.label)


def test_ties_break_by_schema_feature_order(preprocessor: Preprocessor) -> None:
    attribution = _attribution_for(preprocessor, dict.fromkeys(FEATURES, 0.01))
    record = {
        "gender": "Female", "SeniorCitizen": 0, "Partner": "No", "Dependents": "No", "tenure": 1,
        "PhoneService": "Yes", "MultipleLines": "No", "InternetService": "DSL",
        "OnlineSecurity": "No", "OnlineBackup": "No", "DeviceProtection": "No",
        "TechSupport": "No", "StreamingTV": "No", "StreamingMovies": "No",
        "Contract": "Month-to-month", "PaperlessBilling": "Yes",
        "PaymentMethod": "Mailed check", "MonthlyCharges": 50.0, "TotalCharges": 50.0,
    }  # fmt: skip
    factors = aggregate_factors(attribution, preprocessor.feature_groups, record, False)
    assert [f.feature for f in factors] == list(FEATURES[:5])  # 同分 → 依 FEATURES 順序


def test_zero_impact_is_decrease_and_exactly_five(preprocessor: Preprocessor) -> None:
    record = {name: 0 for name in FEATURES}
    record.update(gender="Female", Partner="No", Dependents="No", PhoneService="Yes")
    record.update(MultipleLines="No", InternetService="No", Contract="One year")
    record.update(PaperlessBilling="No", PaymentMethod="Mailed check", tenure=3)
    for name in ("OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport"):
        record[name] = "No internet service"
    record["StreamingTV"] = record["StreamingMovies"] = "No internet service"
    factors = aggregate_factors(np.zeros(N_FEATURES), preprocessor.feature_groups, record, False)
    assert len(factors) == 5
    assert {f.direction for f in factors} == {"decrease"}


def test_estimated_total_charges_label_and_equivalence_with_explicit_value(
    make_service: Callable[..., PredictionService],
    fake_runner: Callable[..., Any],
    preprocessor: Preprocessor,
    record: Callable[..., dict[str, Any]],
) -> None:
    """AC-1.14：省略 TotalCharges 與填入估算值，進入模型的向量與預測完全相同。"""
    runner_a, runner_b = fake_runner(), fake_runner()
    attribution = _attribution_for(preprocessor, {"TotalCharges": 0.3})
    omitted = CustomerFeatures.model_validate(record(tenure=10, MonthlyCharges=50.0))
    explicit = CustomerFeatures.model_validate(
        record(tenure=10, MonthlyCharges=50.0, TotalCharges=500)
    )
    a = make_service(runner_a, attribution).predict(omitted)
    b = make_service(runner_b, attribution).predict(explicit)

    assert np.array_equal(runner_a.calls[0], runner_b.calls[0])
    assert a.probability == b.probability
    assert (a.total_charges.value, a.total_charges.is_estimated) == (500.0, True)
    assert (b.total_charges.value, b.total_charges.is_estimated) == (500.0, False)
    assert a.top_factors[0].label == "累計費用：$500.00（估算）"
    assert b.top_factors[0].label == "累計費用：$500.00"


@pytest.mark.parametrize(
    ("overrides", "expected_value", "estimated"),
    [
        ({"TotalCharges": 1200.005}, 1200.01, False),  # AC-1.17 手填 half-up
        ({"tenure": 1, "MonthlyCharges": 20.005}, 20.01, True),  # 估算值 half-up
        ({"TotalCharges": 0}, 0.0, False),
        ({"tenure": 0, "MonthlyCharges": 80.0}, 0.0, True),  # tenure=0 → 估算 0
    ],
)
def test_total_charges_half_up(
    make_service: Callable[..., PredictionService],
    fake_runner: Callable[..., Any],
    preprocessor: Preprocessor,
    record: Callable[..., dict[str, Any]],
    overrides: dict[str, Any],
    expected_value: float,
    estimated: bool,
) -> None:
    service = make_service(fake_runner(), np.zeros(N_FEATURES))
    response = service.predict(CustomerFeatures.model_validate(record(**overrides)))
    assert response.total_charges.value == expected_value
    assert response.total_charges.is_estimated is estimated


def test_same_input_gives_identical_response(
    make_service: Callable[..., PredictionService],
    fake_runner: Callable[..., Any],
    preprocessor: Preprocessor,
    features: CustomerFeatures,
) -> None:
    attribution = _attribution_for(preprocessor, {"Contract": 0.2, "tenure": 0.1})
    service = make_service(fake_runner(), attribution)
    assert service.predict(features) == service.predict(features)


def test_over_limit_estimate_defense_raises_validation_error_with_reason(
    make_service: Callable[..., PredictionService],
    fake_runner: Callable[..., Any],
    preprocessor: Preprocessor,
    record: Callable[..., dict[str, Any]],
) -> None:
    """schema 已先擋下；若繞過驗證，service 以 EstimateOverLimitError 的 reason 回 422。"""
    bypass = CustomerFeatures.model_construct(
        **record(tenure=72, MonthlyCharges=200.0, TotalCharges=None)
    )
    service = make_service(fake_runner(), np.zeros(N_FEATURES))
    with pytest.raises(AppError) as info:
        service.predict(bypass)
    assert info.value.code is ErrorCode.VALIDATION_ERROR
    (detail,) = info.value.details
    assert (detail.field, detail.type, detail.row) == ("TotalCharges", "out_of_range", None)
    assert detail.reason == "累計費用估算值為 14,400.00，超過上限 10,000，請手動填寫累計費用"
