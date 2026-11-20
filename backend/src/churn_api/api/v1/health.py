"""`GET /api/v1/health`：健康檢查與模型版本（design.md 6.5.1）。"""

from fastapi import APIRouter

from churn_api.dependencies import ModelStateDep
from churn_api.errors import AppError, ErrorCode, error_responses
from churn_api.schemas.common import HealthResponse

router = APIRouter(tags=["系統"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="健康檢查",
    description="服務正常且模型已載入時回 200 並附模型版本；模型缺檔、雜湊不符或載入失敗時回 503 "
    "`MODEL_UNAVAILABLE`（服務本身仍在運作）。供 docker healthcheck 使用。",
    responses=error_responses(ErrorCode.MODEL_UNAVAILABLE),
)
def get_health(state: ModelStateDep) -> HealthResponse:
    if state.bundle is None:
        raise AppError(ErrorCode.MODEL_UNAVAILABLE)
    return HealthResponse(status="ok", model_loaded=True, model=state.bundle.model_info)
