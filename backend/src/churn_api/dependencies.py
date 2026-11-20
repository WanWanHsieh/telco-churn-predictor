"""FastAPI `Depends` 取用函式（design.md 1.3）。

物件由 `main.py` 的 lifespan 組裝並放進 `app.state`；測試以 `app.dependency_overrides` 替換。
"""

from typing import Annotated

from fastapi import Depends, Request

from churn_api.inference.artifacts import ModelState
from churn_api.settings import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_model_state(request: Request) -> ModelState:
    """模型載入結果；lifespan 尚未執行時視為不可用（回 503，而不是 500）。"""
    state = getattr(request.app.state, "model_state", None)
    return state if isinstance(state, ModelState) else ModelState()


SettingsDep = Annotated[Settings, Depends(get_settings)]
ModelStateDep = Annotated[ModelState, Depends(get_model_state)]
