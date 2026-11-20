"""單筆預測的請求／回應型別（design.md 6.2、6.5.3）。

`CustomerFeatures` 是單筆請求本體，也是批次每一列的驗證模型（兩邊規則完全相同）：
- 嚴格型別：`SeniorCitizen`、`tenure` 只接受整數（拒絕 `true`、`1.0`、`10.0`、字串）；
  金額只接受數字（拒絕字串、布林、NaN／Infinity）。
- `extra="forbid"`：拼錯的欄名回 422。
- 電話／網路連動一致性、TotalCharges 估算值上限，都以欄位驗證器實作，
  錯誤的 `loc` 指向子欄位，因此會與其他欄位錯誤一併列出。
"""

from typing import Annotated, Any, Final, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from churn_api.schemas.common import ModelInfo, RiskThresholds
from churn_core.examples import HIGH_RISK_EXAMPLE, LOW_RISK_EXAMPLE
from churn_core.imputation import estimate_total_charges, over_limit_reason
from churn_core.schema import (
    INTERNET_ADDON_FEATURES,
    MONTHLY_CHARGES_RANGE,
    NO_INTERNET_SERVICE,
    NO_PHONE_SERVICE,
    TENURE_RANGE,
    TOTAL_CHARGES_RANGE,
    ContractValue,
    Gender,
    InternetAddon,
    InternetServiceValue,
    MultipleLinesValue,
    PaymentMethodValue,
    YesNo,
)

RiskLevel = Literal["low", "medium", "high"]
EXPLANATION_METHOD: Final = "integrated_gradients"


def _senior_citizen_choice(value: int) -> int:
    if value not in (0, 1):
        raise PydanticCustomError("invalid_choice", "是否為年長者需為整數 0 或 1")
    return value


# 嚴格整數（拒絕 bool、float、字串）；範圍違規回 out_of_range
_SeniorCitizen = Annotated[
    int,
    Strict(),
    AfterValidator(_senior_citizen_choice),
    Field(description="是否為年長者（65 歲以上）：0＝否、1＝是（嚴格整數）"),
]
_Tenure = Annotated[
    int,
    Strict(),
    Field(
        ge=TENURE_RANGE[0],
        le=TENURE_RANGE[1],
        description='在網月數，0 至 72 的整數（嚴格整數，10.5、"10" 皆拒絕）',
    ),
]
_MonthlyCharges = Annotated[
    float,
    Field(
        ge=MONTHLY_CHARGES_RANGE[0],
        le=MONTHLY_CHARGES_RANGE[1],
        allow_inf_nan=False,
        description="月費，0 至 200（數字型別，字串拒絕）",
    ),
]


class CustomerFeatures(BaseModel):
    """單筆顧客特徵（19 欄；`TotalCharges` 可省略或為 null，改以 tenure × MonthlyCharges 估算）。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "examples": [dict(HIGH_RISK_EXAMPLE), dict(LOW_RISK_EXAMPLE)],
        },
    )

    gender: Gender = Field(description="性別")
    SeniorCitizen: _SeniorCitizen
    Partner: YesNo = Field(description="有無配偶")
    Dependents: YesNo = Field(description="有無撫養對象")
    tenure: _Tenure
    PhoneService: YesNo = Field(description="電話服務")
    MultipleLines: MultipleLinesValue = Field(
        description="多線電話；PhoneService=No 時必須為 No phone service，反之亦然"
    )
    InternetService: InternetServiceValue = Field(description="網路服務")
    OnlineSecurity: InternetAddon = Field(description="線上安全服務")
    OnlineBackup: InternetAddon = Field(description="線上備份服務")
    DeviceProtection: InternetAddon = Field(description="裝置保護服務")
    TechSupport: InternetAddon = Field(description="技術支援服務")
    StreamingTV: InternetAddon = Field(description="串流電視")
    StreamingMovies: InternetAddon = Field(description="串流電影")
    Contract: ContractValue = Field(description="合約類型")
    PaperlessBilling: YesNo = Field(description="電子帳單")
    PaymentMethod: PaymentMethodValue = Field(description="付款方式")
    MonthlyCharges: _MonthlyCharges
    TotalCharges: float | None = Field(
        default=None,
        ge=TOTAL_CHARGES_RANGE[0],
        le=TOTAL_CHARGES_RANGE[1],
        allow_inf_nan=False,
        validate_default=True,
        description=(
            "累計費用，0 至 10,000；省略或 null 時以 tenure × MonthlyCharges 估算"
            "（估算值亦須 ≤ 10,000）。手填值與估算值皆 half-up 取到 2 位小數"
        ),
    )

    @field_validator("MultipleLines")
    @classmethod
    def _check_phone_consistency(cls, value: str, info: ValidationInfo) -> str:
        phone = info.data.get("PhoneService")
        if phone is not None and (phone == "No") != (value == NO_PHONE_SERVICE):
            raise PydanticCustomError(
                "inconsistent", "與 PhoneService 不一致（無電話服務時需為 No phone service）"
            )
        return value

    @field_validator(*INTERNET_ADDON_FEATURES)
    @classmethod
    def _check_internet_consistency(cls, value: str, info: ValidationInfo) -> str:
        internet = info.data.get("InternetService")
        if internet is not None and (internet == "No") != (value == NO_INTERNET_SERVICE):
            raise PydanticCustomError(
                "inconsistent", "與 InternetService 不一致（無網路服務時需為 No internet service）"
            )
        return value

    @field_validator("TotalCharges")
    @classmethod
    def _check_estimate_limit(cls, value: float | None, info: ValidationInfo) -> float | None:
        """TotalCharges 省略／null 時，估算值（四捨五入後）也不得超過上限（design.md 6.2）。"""
        if value is not None:
            return value
        tenure = info.data.get("tenure")
        monthly = info.data.get("MonthlyCharges")
        if tenure is None or monthly is None:
            return value  # 這兩欄本身已有各自的錯誤
        estimate = estimate_total_charges(tenure, monthly)
        if estimate > TOTAL_CHARGES_RANGE[1]:
            raise PydanticCustomError("out_of_range", over_limit_reason(estimate))
        return value

    def to_record(self) -> dict[str, Any]:
        """19 欄的純 Python 字典（欄位順序同 schema.FEATURES）。"""
        return self.model_dump()


class TotalChargesInfo(BaseModel):
    value: float = Field(description="實際用於預測的累計費用（half-up 到 2 位小數）")
    is_estimated: bool = Field(description="是否為估算值（tenure × MonthlyCharges）")


class Factor(BaseModel):
    feature: str = Field(description="原始欄名，只作前端 key，不顯示")
    label: str = Field(description="中文顯示名，格式「欄位中文：值中文」")
    direction: Literal["increase", "decrease"] = Field(
        description="increase＝推高風險；decrease＝拉低風險"
    )
    impact: float = Field(description="帶正負號的機率影響值（3 位小數）")


class Explanation(BaseModel):
    method: Literal["integrated_gradients"] = EXPLANATION_METHOD
    baseline_probability: float = Field(description="「平均顧客」的流失機率")


class PredictionResponse(BaseModel):
    """單筆預測結果：機率、等級、切點、模型資訊、累計費用資訊與前 5 大因素。"""

    probability: float = Field(description="流失機率（0–1，3 位小數）")
    risk_level: RiskLevel = Field(description="依四捨五入後的機率判定")
    risk_thresholds: RiskThresholds
    model: ModelInfo
    total_charges: TotalChargesInfo
    top_factors: list[Factor] = Field(description="恰 5 筆，依 abs(impact) 由大到小")
    explanation: Explanation

    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra={
            "examples": [
                {
                    "probability": 0.724,
                    "risk_level": "high",
                    "risk_thresholds": {"medium": 0.30, "high": 0.60},
                    "model": {
                        "name": "keras_mlp",
                        "display_name": "Keras 神經網路",
                        "version": "20261120-a1b2c3d4",
                        "trained_at": "2026-11-20T08:00:00Z",
                    },
                    "total_charges": {"value": 100.0, "is_estimated": True},
                    "top_factors": [
                        {
                            "feature": "Contract",
                            "label": "合約類型：月繳",
                            "direction": "increase",
                            "impact": 0.183,
                        },
                        {
                            "feature": "tenure",
                            "label": "在網月數：1 個月",
                            "direction": "increase",
                            "impact": 0.142,
                        },
                        {
                            "feature": "InternetService",
                            "label": "網路服務：光纖",
                            "direction": "increase",
                            "impact": 0.095,
                        },
                        {
                            "feature": "PaymentMethod",
                            "label": "付款方式：電子支票",
                            "direction": "increase",
                            "impact": 0.061,
                        },
                        {
                            "feature": "TechSupport",
                            "label": "技術支援服務：無",
                            "direction": "increase",
                            "impact": 0.033,
                        },
                    ],
                    "explanation": {
                        "method": "integrated_gradients",
                        "baseline_probability": 0.231,
                    },
                }
            ]
        },
    )
