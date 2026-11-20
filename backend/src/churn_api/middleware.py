"""請求脈絡 middleware：X-Request-ID 與存取 log（design.md 6.1、第 8 節）。

以純 ASGI 實作（不用 BaseHTTPMiddleware），並放在最外層，讓所有回應（含 CORS 預檢、
例外處理器產生的錯誤回應）都帶有 `X-Request-ID`。
未預期例外在這裡攔下並轉成 500 `INTERNAL_ERROR`（堆疊只進 log）。
"""

import logging
import re
import time
import uuid
from typing import Final

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from churn_api.errors import unhandled_exception_response
from churn_api.logging_config import log_event, request_id_var

REQUEST_ID_HEADER: Final = "X-Request-ID"
# 沿用請求帶來的 ID 時只接受安全字元，避免注入 log 或標頭
_VALID_REQUEST_ID: Final = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

access_logger = logging.getLogger("churn_api.access")


def resolve_request_id(raw: str | None) -> str:
    """請求有帶合法的 X-Request-ID 就沿用，否則產生 UUID4。"""
    if raw is not None and _VALID_REQUEST_ID.fullmatch(raw):
        return raw
    return str(uuid.uuid4())


class RequestContextMiddleware:
    """設定 request id、回應加 `X-Request-ID`、輸出 `http_request` 存取 log。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_id = next(
            (
                value.decode("latin-1")
                for name, value in scope["headers"]
                if name.lower() == b"x-request-id"
            ),
            None,
        )
        request_id = resolve_request_id(raw_id)
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_with_id)
            except Exception as exc:
                if response_started:
                    raise  # 回應已開始送出，無法改寫；交給伺服器中斷連線
                response = unhandled_exception_response(None, exc)
                await response(scope, receive, send_with_id)
        finally:
            client = scope.get("client")
            log_event(
                access_logger,
                logging.INFO,
                "http_request",
                f"{scope['method']} {scope['path']} {status_code}",
                method=scope["method"],
                path=scope["path"],  # 只記路徑，不記 query 與本體
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                client=client[0] if client else None,
            )
            request_id_var.reset(token)
