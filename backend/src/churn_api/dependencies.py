"""FastAPI `Depends` 取用函式（design.md 1.3）。

物件由 `main.py` 的 lifespan 組裝並放進 `app.state`；測試以 `app.dependency_overrides` 替換。
"""

from typing import Annotated

from fastapi import Depends, Request

from churn_api.errors import AppError, ErrorCode
from churn_api.inference.artifacts import ModelState
from churn_api.services.batch_service import BatchService
from churn_api.services.metrics_service import MetricsService
from churn_api.services.prediction_service import PredictionService
from churn_api.settings import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_model_state(request: Request) -> ModelState:
    """模型載入結果；lifespan 尚未執行時視為不可用（回 503，而不是 500）。"""
    state = getattr(request.app.state, "model_state", None)
    return state if isinstance(state, ModelState) else ModelState()


def get_prediction_service(request: Request) -> PredictionService:
    """模型不可用（未載入或載入失敗）時回 503 `MODEL_UNAVAILABLE`。"""
    service = getattr(request.app.state, "prediction_service", None)
    if not isinstance(service, PredictionService):
        raise AppError(ErrorCode.MODEL_UNAVAILABLE)
    return service


def get_batch_service(request: Request) -> BatchService:
    service = getattr(request.app.state, "batch_service", None)
    if not isinstance(service, BatchService):
        raise AppError(ErrorCode.MODEL_UNAVAILABLE)
    return service


def get_metrics_service(request: Request) -> MetricsService:
    """成效資料不依賴模型；lifespan 尚未執行時視為缺檔（404）。"""
    service = getattr(request.app.state, "metrics_service", None)
    return service if isinstance(service, MetricsService) else MetricsService(None)


SettingsDep = Annotated[Settings, Depends(get_settings)]
ModelStateDep = Annotated[ModelState, Depends(get_model_state)]
PredictionServiceDep = Annotated[PredictionService, Depends(get_prediction_service)]
BatchServiceDep = Annotated[BatchService, Depends(get_batch_service)]
MetricsServiceDep = Annotated[MetricsService, Depends(get_metrics_service)]
