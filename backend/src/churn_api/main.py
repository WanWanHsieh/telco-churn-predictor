"""應用程式組裝：`create_app`、lifespan、CORS、GZip（design.md 1.3、5.3）。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from churn_api import __version__
from churn_api.api.v1.router import api_router
from churn_api.errors import install_exception_handlers
from churn_api.inference.artifacts import ArtifactLoader, load_artifacts, load_model_state
from churn_api.logging_config import configure_logging, log_event
from churn_api.middleware import RequestContextMiddleware
from churn_api.settings import Settings

logger = logging.getLogger("churn_api.main")

API_DESCRIPTION = (
    "Telco 顧客流失預測 API：單筆預測與主要影響因素、模型成效、批次 CSV 預測。"
    "模型以公開範例資料訓練，僅供展示，不可用於真實決策。"
)


def create_app(
    settings: Settings | None = None, *, artifact_loader: ArtifactLoader = load_artifacts
) -> FastAPI:
    """建立應用程式。

    設定不合法（例如風險切點順序錯誤）時 `Settings()` 會拋例外，服務拒絕啟動；
    模型載入失敗則只標記不可用，服務照常啟動（health 與預測回 503）。
    `artifact_loader` 供測試注入。
    """
    settings = settings or Settings()
    configure_logging(settings.log_level, settings.app_env)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.model_state = load_model_state(settings.model_dir, artifact_loader)
        log_event(logger, logging.INFO, "startup_complete", "服務啟動完成")
        yield

    app = FastAPI(
        title="Telco 顧客流失預測 API",
        version=__version__,
        description=API_DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.settings = settings

    install_exception_handlers(app)
    app.include_router(api_router)

    # add_middleware 後加入者在外層：RequestContext（最外）→ CORS → GZip → 路由
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,  # 白名單，不使用 *（NFR-8）
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )
    app.add_middleware(RequestContextMiddleware)
    return app


# uvicorn 入口：`uvicorn churn_api.main:app`
app = create_app()
