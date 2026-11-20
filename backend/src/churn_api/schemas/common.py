"""共用型別（design.md 6.2、6.3、6.5.1）：ModelInfo、RiskThresholds、錯誤格式、健康檢查。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ErrorDetailType = Literal[
    "missing",
    "invalid_type",
    "invalid_choice",
    "out_of_range",
    "inconsistent",
    "extra_field",
    "missing_column",
]


class ModelInfo(BaseModel):
    """預測所用模型的資訊。"""

    name: str = Field(description="模型代號", examples=["keras_mlp"])
    display_name: str = Field(description="畫面顯示名稱", examples=["Keras 神經網路"])
    version: str = Field(
        description="模型版本（YYYYMMDD-雜湊前 8 碼）", examples=["20261120-a1b2c3d4"]
    )
    trained_at: str = Field(
        description="訓練時間（ISO 8601 UTC）", examples=["2026-11-20T08:00:00Z"]
    )


class RiskThresholds(BaseModel):
    """風險分級切點：p < medium 為低；medium <= p < high 為中；p >= high 為高。"""

    medium: float = Field(description="中風險下限", examples=[0.30])
    high: float = Field(description="高風險下限", examples=[0.60])


class ErrorDetail(BaseModel):
    """欄位或列級錯誤。"""

    model_config = ConfigDict(frozen=True)

    field: str | None = Field(description="原始欄名；整份檔案層級的錯誤為 null")
    row: int | None = Field(description="批次才有，與 Excel 列號一致；單筆為 null")
    type: ErrorDetailType = Field(description="錯誤類型")
    reason: str = Field(description="繁體中文的具體原因")


class ErrorBody(BaseModel):
    code: str = Field(description="機器判斷用的錯誤碼", examples=["VALIDATION_ERROR"])
    message: str = Field(description="繁體中文訊息，不含路徑或堆疊")
    details: list[ErrorDetail] = Field(description="欄位／列級錯誤，可為空陣列")
    meta: dict[str, Any] | None = Field(description="補充資訊（例如上限值、錯誤總數）")
    request_id: str = Field(description="與 X-Request-ID 回應標頭相同，方便對照 log")


class ErrorResponse(BaseModel):
    """所有非 2xx 回應的統一格式。"""

    error: ErrorBody


class HealthResponse(BaseModel):
    """健康檢查（模型已載入）。"""

    status: Literal["ok"] = "ok"
    model_loaded: bool = Field(description="模型是否已載入")
    model: ModelInfo

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "model_loaded": True,
                    "model": {
                        "name": "keras_mlp",
                        "display_name": "Keras 神經網路",
                        "version": "20261120-a1b2c3d4",
                        "trained_at": "2026-11-20T08:00:00Z",
                    },
                }
            ]
        }
    )
