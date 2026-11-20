"""結構化 JSON log（design.md 第 8 節）：標準庫 logging＋自寫 Formatter。

- 一行一個 JSON，欄位：ts（ISO 8601 UTC）、level、logger、event、message、request_id，
  以及事件專屬欄位（以 `extra` 傳入）。
- 不記錄請求本體、特徵值、上傳內容；呼叫端只能傳入欄位名、計數、耗時等中繼資料。
- 5xx 的完整堆疊以 `exc_info` 寫入 log（只進 log，不進回應）。
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO

# 目前請求的 request id（由 middleware 設定，formatter 讀取）
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

APP_LOGGER_NAME = "churn_api"
_HANDLER_MARK = "_churn_api_handler"

# LogRecord 本身的屬性；其餘 `extra` 欄位才視為事件專屬欄位
_STANDARD_ATTRS = frozenset(logging.LogRecord("", logging.INFO, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
    "event",
}


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}


def _iso_utc(created: float) -> str:
    return (
        datetime.fromtimestamp(created, UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class JsonFormatter(logging.Formatter):
    """一行一個 JSON 的 formatter。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": _iso_utc(record.created),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "log"),
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        payload.update(_extra_fields(record))
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class DevFormatter(logging.Formatter):
    """development 用的人類可讀格式。"""

    def format(self, record: logging.LogRecord) -> str:
        extras = " ".join(f"{k}={v}" for k, v in _extra_fields(record).items())
        rid = request_id_var.get()
        parts = [
            _iso_utc(record.created),
            f"{record.levelname:<8}",
            record.name,
            str(getattr(record, "event", "log")),
            record.getMessage(),
        ]
        if rid:
            parts.append(f"request_id={rid}")
        if extras:
            parts.append(extras)
        text = " ".join(parts)
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        return text


class _StdoutHandler(logging.StreamHandler[TextIO]):
    """每次輸出時才取 `sys.stdout`，避免綁定到已被關閉的（測試用）串流。"""

    def __init__(self) -> None:
        logging.Handler.__init__(self)

    @property
    def stream(self) -> TextIO:
        return sys.stdout

    @stream.setter
    def stream(self, value: TextIO) -> None:  # pragma: no cover - 與父類別介面相容
        return None


def configure_logging(
    level: str = "INFO", app_env: str = "production", stream: TextIO | None = None
) -> logging.Handler:
    """設定 `churn_api` 與 uvicorn 的 logger，輸出到 stdout（或指定的 stream）。

    可重複呼叫：只會移除並重建本模組安裝過的 handler，不動其他 handler。
    uvicorn 的存取 log 關閉（改由 middleware 輸出含 request_id 的 http_request 事件）。
    """
    handler: logging.Handler = logging.StreamHandler(stream) if stream else _StdoutHandler()
    handler.setFormatter(DevFormatter() if app_env == "development" else JsonFormatter())
    setattr(handler, _HANDLER_MARK, True)

    for name in (APP_LOGGER_NAME, "uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        for old in [h for h in logger.handlers if getattr(h, _HANDLER_MARK, False)]:
            logger.removeHandler(old)
        if name != APP_LOGGER_NAME:
            logger.handlers.clear()  # 取代 uvicorn 預設的純文字 handler
        logger.addHandler(handler)
        logger.propagate = False
        logger.setLevel(level)

    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True
    return handler


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str = "",
    *,
    exc_info: BaseException | None = None,
    **fields: Any,
) -> None:
    """輸出一筆帶 `event` 與專屬欄位的 log。`fields` 不得含請求本體或特徵值。"""
    logger.log(level, message or event, exc_info=exc_info, extra={"event": event, **fields})
