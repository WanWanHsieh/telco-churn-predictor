"""高／低風險範例（design.md 6.7）。

單一定義，供批次範本 CSV、測試、模型暖機與前端「載入範例」對照使用。
鍵與值皆為 API 請求本體格式；高風險範例省略 TotalCharges（示範估算），低風險範例填 2100.0。
皆為唯讀（MappingProxyType）；需要可修改的副本請用 `dict(...)` 複製。
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

type ExampleValue = str | int | float

HIGH_RISK_EXAMPLE: Final[Mapping[str, ExampleValue]] = MappingProxyType(
    {
        "gender": "Female",
        "SeniorCitizen": 0,
        "Partner": "No",
        "Dependents": "No",
        "tenure": 1,
        "PhoneService": "Yes",
        "MultipleLines": "No",
        "InternetService": "Fiber optic",
        "OnlineSecurity": "No",
        "OnlineBackup": "No",
        "DeviceProtection": "No",
        "TechSupport": "No",
        "StreamingTV": "Yes",
        "StreamingMovies": "Yes",
        "Contract": "Month-to-month",
        "PaperlessBilling": "Yes",
        "PaymentMethod": "Electronic check",
        "MonthlyCharges": 100.0,
    }
)

LOW_RISK_EXAMPLE: Final[Mapping[str, ExampleValue]] = MappingProxyType(
    {
        "gender": "Male",
        "SeniorCitizen": 0,
        "Partner": "Yes",
        "Dependents": "Yes",
        "tenure": 70,
        "PhoneService": "Yes",
        "MultipleLines": "Yes",
        "InternetService": "No",
        "OnlineSecurity": "No internet service",
        "OnlineBackup": "No internet service",
        "DeviceProtection": "No internet service",
        "TechSupport": "No internet service",
        "StreamingTV": "No internet service",
        "StreamingMovies": "No internet service",
        "Contract": "Two year",
        "PaperlessBilling": "No",
        "PaymentMethod": "Credit card (automatic)",
        "MonthlyCharges": 30.0,
        "TotalCharges": 2100.0,
    }
)

EXAMPLES: Final[Mapping[str, Mapping[str, ExampleValue]]] = MappingProxyType(
    {
        "high_risk": HIGH_RISK_EXAMPLE,
        "low_risk": LOW_RISK_EXAMPLE,
    }
)
