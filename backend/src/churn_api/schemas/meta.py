"""`GET /api/v1/meta` 回應（design.md 6.5.2）。"""

from pydantic import BaseModel, ConfigDict, Field

from churn_api.schemas.common import RiskThresholds


class BatchLimits(BaseModel):
    max_file_bytes: int = Field(description="批次上傳檔案大小上限（位元組）")
    max_rows: int = Field(description="批次上傳資料列數上限")


class NumericRange(BaseModel):
    min: int | float = Field(description="下限（含）")
    max: int | float = Field(description="上限（含）")


class InputRanges(BaseModel):
    tenure: NumericRange
    MonthlyCharges: NumericRange
    TotalCharges: NumericRange


class MetaResponse(BaseModel):
    """前端需要的設定；不依賴模型是否載入。"""

    risk_thresholds: RiskThresholds
    batch_limits: BatchLimits
    input_ranges: InputRanges

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "risk_thresholds": {"medium": 0.30, "high": 0.60},
                    "batch_limits": {"max_file_bytes": 5242880, "max_rows": 10000},
                    "input_ranges": {
                        "tenure": {"min": 0, "max": 72},
                        "MonthlyCharges": {"min": 0, "max": 200},
                        "TotalCharges": {"min": 0, "max": 10000},
                    },
                }
            ]
        }
    )
