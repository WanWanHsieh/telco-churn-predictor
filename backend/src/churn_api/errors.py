"""統一錯誤處理（design.md 6.3、NFR-7）。

- 錯誤碼總表 `ERROR_SPECS`：錯誤碼 → HTTP 狀態與預設繁中訊息。
- `AppError`：service／路由層主動拋出的業務錯誤；`details[].reason` 可由呼叫端直接帶入
  （例如 `churn_core.imputation.EstimateOverLimitError` 的 field／type／reason），不需新錯誤碼。
- Pydantic 驗證錯誤翻譯為繁中 `reason`（`translate_pydantic_errors`），批次可帶 `row`。
- 所有錯誤回應都是 `{error:{code,message,details,meta,request_id}}`，
  不含堆疊、路徑、套件版本；未預期例外回 500 `INTERNAL_ERROR`，堆疊只進 log。
"""

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from churn_api.logging_config import log_event, request_id_var
from churn_api.schemas.common import ErrorDetail, ErrorDetailType, ErrorResponse
from churn_core.labels import FIELD_LABELS
from churn_core.schema import (
    LEGAL_VALUES,
    MONTHLY_CHARGES_RANGE,
    TENURE_RANGE,
    TOTAL_CHARGES_RANGE,
)

logger = logging.getLogger("churn_api.errors")


class ErrorCode(StrEnum):
    FILE_EMPTY = "FILE_EMPTY"
    METRICS_NOT_FOUND = "METRICS_NOT_FOUND"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    TOO_MANY_ROWS = "TOO_MANY_ROWS"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    MISSING_COLUMNS = "MISSING_COLUMNS"
    INVALID_ROWS = "INVALID_ROWS"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"


@dataclass(frozen=True)
class ErrorSpec:
    status: int
    message: str


# 錯誤碼總表（design.md 6.3）
ERROR_SPECS: Final[Mapping[ErrorCode, ErrorSpec]] = {
    ErrorCode.FILE_EMPTY: ErrorSpec(400, "上傳的檔案是空的，或只有表頭，請確認內容。"),
    ErrorCode.METRICS_NOT_FOUND: ErrorSpec(404, "尚無模型成效資料。"),
    ErrorCode.NOT_FOUND: ErrorSpec(404, "找不到要求的資源。"),
    ErrorCode.METHOD_NOT_ALLOWED: ErrorSpec(405, "不支援此請求方法。"),
    ErrorCode.FILE_TOO_LARGE: ErrorSpec(413, "檔案過大，超過上傳大小上限。"),
    ErrorCode.TOO_MANY_ROWS: ErrorSpec(413, "資料列數超過上限。"),
    ErrorCode.UNSUPPORTED_FILE_TYPE: ErrorSpec(415, "僅支援 UTF-8 編碼的 CSV 檔案。"),
    ErrorCode.VALIDATION_ERROR: ErrorSpec(422, "輸入資料有誤，請檢查標示的欄位。"),
    ErrorCode.MISSING_COLUMNS: ErrorSpec(422, "檔案缺少必要欄位。"),
    ErrorCode.INVALID_ROWS: ErrorSpec(422, "檔案中有不合法的資料列，整份檔案未處理。"),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(500, "服務暫時無法使用，請稍後再試。"),
    ErrorCode.MODEL_UNAVAILABLE: ErrorSpec(503, "模型尚未載入，服務暫時無法使用。"),
}


class AppError(Exception):
    """業務錯誤：由 service／路由層拋出，統一轉成 6.3 格式。

    `message` 省略時使用總表的預設訊息；`details` 的 `reason` 由呼叫端提供（繁中）。
    """

    def __init__(
        self,
        code: ErrorCode,
        *,
        message: str | None = None,
        details: Sequence[ErrorDetail] = (),
        meta: Mapping[str, Any] | None = None,
    ) -> None:
        spec = ERROR_SPECS[code]
        self.code = code
        self.status_code = spec.status
        self.message = message or spec.message
        self.details = list(details)
        self.meta = dict(meta) if meta is not None else None
        super().__init__(f"{code.value}: {self.message}")


# --------------------------------------------------------------- 回應組裝
def current_request_id() -> str:
    """目前請求的 request id；不在請求脈絡中（例如單元測試）時產生一個新的。"""
    return request_id_var.get() or str(uuid.uuid4())


def build_error_payload(
    code: ErrorCode | str,
    message: str,
    details: Sequence[ErrorDetail] = (),
    meta: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """組出 6.3 格式的字典（`error` 底下五個鍵一定都在）。"""
    return {
        "error": {
            "code": str(code),
            "message": message,
            "details": [d.model_dump() for d in details],
            "meta": dict(meta) if meta is not None else None,
            "request_id": request_id or current_request_id(),
        }
    }


def error_response(
    code: ErrorCode,
    *,
    message: str | None = None,
    details: Sequence[ErrorDetail] = (),
    meta: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    spec = ERROR_SPECS[code]
    payload = build_error_payload(code, message or spec.message, details, meta)
    return JSONResponse(payload, status_code=spec.status, headers=dict(headers or {}))


def error_responses(*codes: ErrorCode) -> dict[int | str, dict[str, Any]]:
    """產生路由的 `responses=`：每個狀態碼帶 `ErrorResponse` 模型與範例（AC-5.2）。"""
    grouped: dict[int, list[ErrorCode]] = {}
    for code in codes:
        grouped.setdefault(ERROR_SPECS[code].status, []).append(code)

    result: dict[int | str, dict[str, Any]] = {}
    for status, group in grouped.items():
        examples = {
            code.value: {
                "summary": code.value,
                "value": build_error_payload(
                    code,
                    ERROR_SPECS[code].message,
                    request_id="6f1c2a9e-1b7d-4d1f-9a55-2b1b8f0c9d11",
                ),
            }
            for code in group
        }
        result[status] = {
            "model": ErrorResponse,
            "description": "、".join(c.value for c in group),
            "content": {"application/json": {"examples": examples}},
        }
    return result


# --------------------------------------------------------------- Pydantic 錯誤翻譯
_SOURCE_PREFIXES: Final = frozenset({"body", "query", "path", "header", "cookie"})
_PASSTHROUGH_TYPES: Final[frozenset[str]] = frozenset(
    {
        "invalid_type",
        "invalid_choice",
        "out_of_range",
        "inconsistent",
        "extra_field",
        "missing_column",
    }
)
_LOWER_BOUND_TYPES: Final = frozenset({"greater_than_equal", "greater_than"})
_UPPER_BOUND_TYPES: Final = frozenset({"less_than_equal", "less_than"})
_CHOICE_TYPES: Final = frozenset({"literal_error", "enum"})


def _num(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,}"


def _field_from_loc(loc: Sequence[Any]) -> str | None:
    """loc → 原始欄名；去掉 body/query 等來源前綴，整份內容層級（無欄名）為 None。"""
    parts = list(loc)
    if parts and parts[0] in _SOURCE_PREFIXES:
        parts = parts[1:]
    if parts and isinstance(parts[0], str):
        return parts[0]
    return None


def _choices_reason(field: str, *, wrong_type: bool) -> str:
    if field == "SeniorCitizen":
        return "是否為年長者需為整數 0 或 1"
    options = "、".join(LEGAL_VALUES[field])
    prefix = "型別錯誤，需為文字，" if wrong_type else "不是合法選項，"
    return f"{prefix}可用值：{options}"


def _numeric_reason(field: str, etype: str) -> str | None:
    """數值欄位的訊息，與 ui.md 3.2 的前端文字一致。"""
    if field == "tenure":
        return f"在網月數需為 {TENURE_RANGE[0]} 至 {TENURE_RANGE[1]} 的整數"
    if field == "MonthlyCharges":
        low, high = _num(MONTHLY_CHARGES_RANGE[0]), _num(MONTHLY_CHARGES_RANGE[1])
        return f"月費需介於 {low} 至 {high} 之間"
    if field == "TotalCharges":
        if etype in _UPPER_BOUND_TYPES:
            return f"累計費用不可超過 {_num(TOTAL_CHARGES_RANGE[1])}"
        return f"累計費用需為 {_num(TOTAL_CHARGES_RANGE[0])} 以上的數字"
    return None


def _translate_one(field: str | None, error: Mapping[str, Any]) -> tuple[ErrorDetailType, str]:
    etype = str(error.get("type", ""))
    label = FIELD_LABELS.get(field or "")

    if etype == "missing":
        return "missing", (f"缺少必填欄位：{label or field}" if field else "缺少必填欄位")
    if etype == "extra_forbidden":
        return "extra_field", "不認識的欄位，請檢查欄位名稱是否拼錯"
    if etype == "json_invalid":
        return "invalid_type", "請求內容不是有效的 JSON"
    if field is None and etype in {"model_attributes_type", "dict_type", "model_type"}:
        return "invalid_type", "請求內容需為 JSON 物件"

    # service／schema 以 PydanticCustomError 自訂的 detail type：msg 即 reason
    if etype in _PASSTHROUGH_TYPES:
        return cast(ErrorDetailType, etype), str(error.get("msg", "輸入不合法"))
    if etype in {"value_error", "assertion_error"}:
        ctx = error.get("ctx") or {}
        reason = str(ctx.get("error", "")) if isinstance(ctx, Mapping) else ""
        return "inconsistent", reason or "欄位之間的內容不一致"

    is_range = etype in _LOWER_BOUND_TYPES | _UPPER_BOUND_TYPES
    if field is not None and (field in LEGAL_VALUES or field == "SeniorCitizen"):
        if etype in _CHOICE_TYPES:
            return "invalid_choice", _choices_reason(field, wrong_type=False)
        return "invalid_type", _choices_reason(field, wrong_type=True)
    if field is not None:
        numeric = _numeric_reason(field, etype)
        if numeric is not None:
            return ("out_of_range" if is_range else "invalid_type"), numeric
    if is_range:
        return "out_of_range", "數值超出允許範圍"
    return "invalid_type", "格式不正確"


def translate_pydantic_errors(
    errors: Sequence[Mapping[str, Any]], *, row: int | None = None
) -> list[ErrorDetail]:
    """Pydantic（`ValidationError.errors()`／`RequestValidationError.errors()`）→ 繁中 details。

    列出所有錯誤（不只第一個）；`row` 為批次的 Excel 列號，單筆為 None。
    不輸出 `input`（使用者輸入值），避免洩漏內容。
    """
    details: list[ErrorDetail] = []
    for error in errors:
        field = _field_from_loc(error.get("loc", ()))
        etype, reason = _translate_one(field, error)
        details.append(ErrorDetail(field=field, row=row, type=etype, reason=reason))
    return details


# --------------------------------------------------------------- 例外處理器
def unhandled_exception_response(request: Request | None, exc: BaseException) -> JSONResponse:
    """未預期例外 → 500 `INTERNAL_ERROR`；完整堆疊只寫進 log，回應只有 code 與 request_id。"""
    log_event(
        logger,
        logging.ERROR,
        "unhandled_exception",
        "未預期的例外",
        exc_info=exc,
        method=request.method if request else None,
        path=request.url.path if request else None,
    )
    return error_response(ErrorCode.INTERNAL_ERROR)


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):  # pragma: no cover - 只是型別窄化
        raise exc
    if exc.status_code >= 500 and exc.code is not ErrorCode.MODEL_UNAVAILABLE:
        log_event(logger, logging.ERROR, "app_error", exc.message, code=exc.code.value)
    return error_response(exc.code, message=exc.message, details=exc.details, meta=exc.meta)


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        raise exc
    details = translate_pydantic_errors(exc.errors())
    # 只記欄位名，不記值（NFR-8）
    log_event(
        logger,
        logging.INFO,
        "validation_failed",
        "請求驗證失敗",
        fields=[d.field for d in details],
    )
    return error_response(ErrorCode.VALIDATION_ERROR, details=details)


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover
        raise exc
    if exc.status_code == 404:
        return error_response(ErrorCode.NOT_FOUND)
    if exc.status_code == 405:
        allow = (exc.headers or {}).get("Allow")
        return error_response(
            ErrorCode.METHOD_NOT_ALLOWED, headers={"Allow": allow} if allow else None
        )
    if exc.status_code >= 500:
        return unhandled_exception_response(request, exc)
    # 其餘 4xx（例如 multipart 解析失敗）屬於請求內容有誤；不回傳框架的原始 detail
    return error_response(ErrorCode.VALIDATION_ERROR)


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    return unhandled_exception_response(request, exc)


def install_exception_handlers(app: FastAPI) -> None:
    """註冊全部例外處理器。"""
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
