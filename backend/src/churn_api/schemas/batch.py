"""批次預測的回應型別（design.md 6.5.5）。"""

from pydantic import BaseModel, ConfigDict, Field

from churn_api.schemas.common import ModelInfo, RiskThresholds
from churn_api.schemas.prediction import CustomerFeatures, RiskLevel


class BatchSummary(BaseModel):
    total: int = Field(description="總筆數")
    high: int = Field(description="高風險筆數")
    medium: int = Field(description="中風險筆數")
    low: int = Field(description="低風險筆數")
    estimated_total_charges: int = Field(description="累計費用為估算值的筆數")


class BatchRow(BaseModel):
    row: int = Field(description="Excel 列號（表頭為第 1 列，第一筆資料為第 2 列）")
    customer_id: str | None = Field(description="customerID 欄的值；沒有該欄或空白為 null")
    probability: float = Field(description="流失機率（0–1，3 位小數）")
    risk_level: RiskLevel
    total_charges_estimated: bool = Field(description="該列累計費用是否為估算值")
    input: CustomerFeatures = Field(
        description="該列 19 個特徵的正規化後值；TotalCharges 為原始值，空白則為 null"
    )


class BatchResponse(BaseModel):
    """批次預測結果；`results` 依檔案原始順序。"""

    summary: BatchSummary
    risk_thresholds: RiskThresholds
    model: ModelInfo
    has_customer_id: bool = Field(description="檔案是否有 customerID 欄")
    ignored_columns: list[str] = Field(description="被忽略的多餘欄位名稱")
    results: list[BatchRow]

    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra={
            "examples": [
                {
                    "summary": {
                        "total": 2,
                        "high": 1,
                        "medium": 0,
                        "low": 1,
                        "estimated_total_charges": 1,
                    },
                    "risk_thresholds": {"medium": 0.30, "high": 0.60},
                    "model": {
                        "name": "keras_mlp",
                        "display_name": "Keras 神經網路",
                        "version": "20261120-a1b2c3d4",
                        "trained_at": "2026-11-20T08:00:00Z",
                    },
                    "has_customer_id": True,
                    "ignored_columns": [],
                    "results": [
                        {
                            "row": 2,
                            "customer_id": "DEMO-HIGH",
                            "probability": 0.724,
                            "risk_level": "high",
                            "total_charges_estimated": True,
                            "input": {
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
                                "TotalCharges": None,
                            },
                        }
                    ],
                }
            ]
        },
    )
