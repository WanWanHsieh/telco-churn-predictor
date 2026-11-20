"""v1 路由彙整：base path `/api/v1`。"""

from fastapi import APIRouter

from churn_api.api.v1 import health, meta

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(meta.router)
