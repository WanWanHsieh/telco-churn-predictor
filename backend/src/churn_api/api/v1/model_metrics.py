"""`GET /api/v1/model/metrics`：成效頁資料（design.md 6.5.4）。"""

from fastapi import APIRouter

from churn_api.dependencies import MetricsServiceDep
from churn_api.errors import ErrorCode, error_responses
from churn_api.schemas.metrics import MetricsResponse

router = APIRouter(tags=["模型成效"])


@router.get(
    "/model/metrics",
    response_model=MetricsResponse,
    summary="模型成效",
    description=(
        "回傳訓練時產生的成效資料（與 `models/metrics.json` 內容相同）：兩個模型在同一份測試集上的"
        "五項指標、混淆矩陣、ROC 曲線、資料筆數、決策門檻與不平衡處理實驗。"
        "啟動時載入記憶體，不依賴預測模型是否載入。"
        "`metrics.json` 不存在時回 404 `METRICS_NOT_FOUND`。"
    ),
    responses=error_responses(ErrorCode.METRICS_NOT_FOUND, ErrorCode.INTERNAL_ERROR),
)
def get_model_metrics(service: MetricsServiceDep) -> MetricsResponse:
    return service.get()
