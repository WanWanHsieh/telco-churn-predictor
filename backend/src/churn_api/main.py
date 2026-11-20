"""應用程式組裝：`create_app`、lifespan、CORS、GZip（design.md 1.3、5.3）。"""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from churn_api import __version__
from churn_api.api.v1.router import api_router
from churn_api.errors import install_exception_handlers
from churn_api.inference.artifacts import (
    ArtifactLoader,
    ModelState,
    load_artifacts,
    load_model_state,
)
from churn_api.inference.explainer import IntegratedGradientsExplainer
from churn_api.inference.model_runner import KerasModelRunner
from churn_api.logging_config import configure_logging, log_event
from churn_api.middleware import RequestContextMiddleware, UnhandledExceptionMiddleware
from churn_api.schemas.common import RiskThresholds
from churn_api.services.batch_service import BatchService
from churn_api.services.metrics_service import MetricsService
from churn_api.services.prediction_service import PredictionService, to_model_info
from churn_api.settings import Settings
from churn_core.examples import HIGH_RISK_EXAMPLE
from churn_core.imputation import impute_total_charges
from churn_core.schema import FEATURES

logger = logging.getLogger("churn_api.main")

API_DESCRIPTION = (
    "Telco 顧客流失預測 API：單筆預測與主要影響因素、模型成效、批次 CSV 預測。"
    "模型以公開範例資料訓練，僅供展示，不可用於真實決策。"
)


def _assemble_services(app: FastAPI, settings: Settings, state: ModelState) -> ModelState:
    """依已驗證的模型產物建立 runner、解釋器（暖機）與 service，放進 `app.state`。

    任何一步失敗（例如暖機例外）都改標記為模型不可用，服務照常啟動（AC-1.9）。
    """
    app.state.prediction_service = None
    app.state.batch_service = None
    bundle = state.bundle
    if bundle is None:
        return state
    started = time.perf_counter()
    try:
        runner = KerasModelRunner(bundle.keras_model)
        explainer = IntegratedGradientsExplainer(
            bundle.keras_model,
            bundle.baseline,
            bundle.baseline_probability,
            steps=settings.ig_steps,
        )
        warm_up_frame = pd.DataFrame([dict(HIGH_RISK_EXAMPLE)], columns=list(FEATURES))
        warm_up_vector = bundle.preprocessor.transform(impute_total_charges(warm_up_frame).frame)
        explainer.warm_up(warm_up_vector[0])
        runner.predict_proba(warm_up_vector)
        thresholds = RiskThresholds(
            medium=settings.risk_medium_threshold, high=settings.risk_high_threshold
        )
        info = to_model_info(bundle.model_info)
        app.state.prediction_service = PredictionService(
            runner, explainer, bundle.preprocessor, info, thresholds
        )
        app.state.batch_service = BatchService(runner, bundle.preprocessor, info, thresholds)
    except Exception as exc:  # 暖機或組裝失敗：標記不可用而不是讓服務掛掉
        reason = f"{type(exc).__name__}: {str(exc)[:300]}"
        log_event(
            logger,
            logging.ERROR,
            "model_load_failed",
            "推論服務組裝失敗",
            exc_info=exc,
            reason=reason,
        )
        app.state.prediction_service = None
        app.state.batch_service = None
        return ModelState(bundle=None, failure_reason=reason)
    log_event(
        logger,
        logging.INFO,
        "inference_ready",
        "推論服務就緒（含 IG 暖機）",
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return state


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
        state = load_model_state(settings.model_dir, artifact_loader)
        app.state.model_state = _assemble_services(app, settings, state)
        app.state.metrics_service = MetricsService.load(settings.model_dir)
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

    # add_middleware 後加入者在外層：
    # RequestContext（最外）→ CORS → UnhandledException → GZip → 路由
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(UnhandledExceptionMiddleware)
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
