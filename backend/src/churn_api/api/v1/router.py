"""v1 路由彙整：base path `/api/v1`。"""

from fastapi import APIRouter

from churn_api.api.v1 import batch, health, meta, model_metrics, predictions

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(meta.router)
api_router.include_router(predictions.router)
api_router.include_router(batch.router)
api_router.include_router(model_metrics.router)
