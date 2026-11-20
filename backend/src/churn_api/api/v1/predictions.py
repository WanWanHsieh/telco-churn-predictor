"""`POST /api/v1/predictions`：單筆預測＋前 5 大因素（design.md 6.5.3）。"""

from typing import Annotated

from fastapi import APIRouter, Body

from churn_api.dependencies import PredictionServiceDep
from churn_api.errors import ErrorCode, error_responses
from churn_api.schemas.prediction import CustomerFeatures, PredictionResponse
from churn_core.examples import HIGH_RISK_EXAMPLE, LOW_RISK_EXAMPLE

router = APIRouter(tags=["預測"])

_REQUEST_EXAMPLES = {
    "high_risk": {
        "summary": "高風險範例（TotalCharges 省略，改以估算）",
        "value": dict(HIGH_RISK_EXAMPLE),
    },
    "low_risk": {"summary": "低風險範例（TotalCharges 手填）", "value": dict(LOW_RISK_EXAMPLE)},
}

_ERRORS = error_responses(ErrorCode.VALIDATION_ERROR, ErrorCode.MODEL_UNAVAILABLE)
_ERRORS[422]["content"]["application/json"]["examples"]["TotalCharges 估算超限"] = {
    "summary": "TotalCharges 省略且 tenure × MonthlyCharges 估算值超過 10,000",
    "value": {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "輸入資料有誤，請檢查標示的欄位。",
            "details": [
                {
                    "field": "TotalCharges",
                    "row": None,
                    "type": "out_of_range",
                    "reason": "累計費用估算值為 14,400.00，超過上限 10,000，請手動填寫累計費用",
                }
            ],
            "meta": None,
            "request_id": "6f1c2a9e-1b7d-4d1f-9a55-2b1b8f0c9d11",
        }
    },
}


@router.post(
    "/predictions",
    response_model=PredictionResponse,
    summary="單筆流失預測",
    description=(
        "輸入 19 個顧客特徵（TotalCharges 可省略，改以 tenure × MonthlyCharges 估算），"
        "回傳流失機率（3 位小數）、風險等級、使用的切點、模型資訊、累計費用資訊，"
        "以及影響最大的前 5 個因素（Integrated Gradients，同一次回應一併回傳）。"
        "相同輸入的結果完全相同。輸入不合法回 422 並列出所有錯誤欄位；模型不可用回 503。"
    ),
    responses=_ERRORS,
)
def create_prediction(
    features: Annotated[CustomerFeatures, Body(openapi_examples=_REQUEST_EXAMPLES)],
    service: PredictionServiceDep,
) -> PredictionResponse:
    return service.predict(features)
