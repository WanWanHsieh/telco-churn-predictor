"""成效資料 service：啟動時載入 `metrics.json` 到記憶體（NFR-3：回應 < 300ms）。

- 缺檔 → 之後的請求回 404 `METRICS_NOT_FOUND`。
- 檔案存在但格式錯 → 之後的請求回 500 `INTERNAL_ERROR`，啟動時 log `metrics_load_failed`。
"""

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from churn_api.errors import AppError, ErrorCode
from churn_api.logging_config import log_event
from churn_api.schemas.metrics import MetricsResponse

logger = logging.getLogger("churn_api.metrics")
METRICS_FILE = "metrics.json"


class MetricsService:
    def __init__(self, metrics: MetricsResponse | None, failure: str | None = None) -> None:
        self._metrics = metrics
        self._failure = failure

    @classmethod
    def load(cls, model_dir: Path) -> MetricsService:
        """讀取並驗證 `metrics.json`；任何問題都只記錄，不讓服務啟動失敗。"""
        path = model_dir / METRICS_FILE
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            log_event(logger, logging.WARNING, "metrics_missing", "找不到 metrics.json")
            return cls(None, failure=None)
        except OSError as exc:
            reason = f"無法讀取 metrics.json（{type(exc).__name__}）"
            log_event(logger, logging.ERROR, "metrics_load_failed", reason, reason=reason)
            return cls(None, failure=reason)
        try:
            return cls(MetricsResponse.model_validate(json.loads(raw)))
        except (
            ValueError,
            ValidationError,
        ) as exc:  # JSONDecodeError、UnicodeDecodeError 皆為 ValueError
            reason = f"metrics.json 格式錯誤：{type(exc).__name__}"
            log_event(
                logger, logging.ERROR, "metrics_load_failed", reason, exc_info=exc, reason=reason
            )
            return cls(None, failure=reason)

    def get(self) -> MetricsResponse:
        if self._metrics is not None:
            return self._metrics
        if self._failure is not None:
            raise AppError(ErrorCode.INTERNAL_ERROR)
        raise AppError(ErrorCode.METRICS_NOT_FOUND)
