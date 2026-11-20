"""批次預測與範本（design.md 6.5.5、6.5.6、6.6）。

上傳以「串流」方式讀取請求本體：先看 `Content-Length`，再逐塊累計，超過上限立即中止
（回 413，不讀完整檔案）；不經 FastAPI 的 `UploadFile` 預先解析，所以大檔不會先被整份收下。
`multipart/form-data` 在上限內才交給 Starlette 的 `MultiPartParser` 解出 `file` 欄位。
程式不寫任何檔案、不記錄內容；Starlette 對 > 1 MB 的檔案暫存於系統暫存目錄，
解析完成後立即 `close()` 刪除（README「已知限制／隱私」說明）。
"""

from collections.abc import AsyncGenerator
from typing import Any, Final

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from churn_api.dependencies import BatchServiceDep, SettingsDep
from churn_api.errors import AppError, ErrorCode, error_responses
from churn_api.schemas.batch import BatchResponse
from churn_api.schemas.common import ErrorDetail
from churn_api.services.csv_parser import TEMPLATE_FILENAME, build_template_csv, parse_batch_csv

router = APIRouter(tags=["批次預測"])

# multipart 邊界與欄位標頭的額外空間（檔案本身的上限另由 max_file_bytes 檢查）
_MULTIPART_OVERHEAD: Final = 64 * 1024


class _BodyTooLarge(MultiPartException):
    """請求本體超過上限；繼承 MultiPartException 讓 Starlette 在中止時關閉已建立的暫存檔。"""


def _file_too_large(max_file_bytes: int) -> AppError:
    return AppError(ErrorCode.FILE_TOO_LARGE, meta={"max_file_bytes": max_file_bytes})


def _invalid_upload(reason: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_ERROR,
        message="請以 multipart/form-data 上傳單一檔案（欄位名稱 file）。",
        details=[ErrorDetail(field="file", row=None, type="missing", reason=reason)],
    )


async def _read_upload(request: Request, max_file_bytes: int) -> tuple[str | None, bytes]:
    """串流讀取並解出 `file` 欄位；回傳（檔名, 位元組）。"""
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise _invalid_upload("請以 multipart/form-data 上傳檔案")

    limit = max_file_bytes + _MULTIPART_OVERHEAD
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise _file_too_large(max_file_bytes)  # 連讀都不讀

    async def limited_stream() -> AsyncGenerator[bytes]:
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > limit:
                raise _BodyTooLarge("body too large")
            yield chunk

    parser = MultiPartParser(request.headers, limited_stream(), max_files=1, max_fields=10)
    try:
        form = await parser.parse()
    except _BodyTooLarge:
        raise _file_too_large(max_file_bytes) from None
    except MultiPartException:
        raise _invalid_upload("上傳內容無法解析") from None

    try:
        upload: Any = form.get("file")
        if not isinstance(upload, UploadFile):
            raise _invalid_upload("缺少 file 欄位（需為檔案）")
        content = await upload.read(max_file_bytes + 1)
        return upload.filename, content
    finally:
        await form.close()


_BATCH_ERRORS = error_responses(
    ErrorCode.FILE_EMPTY,
    ErrorCode.FILE_TOO_LARGE,
    ErrorCode.TOO_MANY_ROWS,
    ErrorCode.UNSUPPORTED_FILE_TYPE,
    ErrorCode.VALIDATION_ERROR,
    ErrorCode.MISSING_COLUMNS,
    ErrorCode.INVALID_ROWS,
    ErrorCode.MODEL_UNAVAILABLE,
)
_BATCH_ERRORS[413]["content"]["application/json"]["examples"]["FILE_TOO_LARGE"]["value"]["error"][
    "meta"
] = {"max_file_bytes": 5242880}
_BATCH_ERRORS[413]["content"]["application/json"]["examples"]["TOO_MANY_ROWS"]["value"]["error"][
    "meta"
] = {"max_rows": 10000, "rows": 12000}
_BATCH_ERRORS[422]["content"]["application/json"]["examples"]["INVALID_ROWS"]["value"][
    "error"
].update(
    {
        "details": [
            {
                "field": "tenure",
                "row": 5,
                "type": "out_of_range",
                "reason": "在網月數需為 0 至 72 的整數",
            }
        ],
        "meta": {"total_errors": 57, "invalid_row_count": 31},
    }
)
_BATCH_ERRORS[422]["content"]["application/json"]["examples"]["MISSING_COLUMNS"]["value"]["error"][
    "details"
] = [
    {
        "field": "Contract",
        "row": None,
        "type": "missing_column",
        "reason": "缺少必要欄位：Contract",
    }
]


@router.post(
    "/predictions/batch",
    response_model=BatchResponse,
    summary="批次 CSV 預測",
    description=(
        "上傳 CSV（UTF-8，可含 BOM；第 1 列為表頭，區分大小寫）。必要欄為 18 個必填特徵，"
        "`TotalCharges` 欄可整欄省略或個別留空（改以 tenure × MonthlyCharges 估算），"
        "`customerID` 選填並原樣帶回，其他欄位忽略。"
        "任何一列不合法即整份拒絕（`details` 只列前 20 筆，`meta.total_errors` 為總數），"
        "不做任何預測。結果依檔案原始順序；上傳內容不會被儲存。"
        "檢查順序：大小 → 副檔名／解碼 → 空檔 → 列數 → 缺欄 → 逐列驗證。"
    ),
    responses=_BATCH_ERRORS,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {
                            "file": {
                                "type": "string",
                                "format": "binary",
                                "description": "CSV 檔案（.csv，UTF-8，上限見 /api/v1/meta）",
                            }
                        },
                    }
                }
            },
        }
    },
)
async def create_batch_prediction(
    request: Request, settings: SettingsDep, service: BatchServiceDep
) -> BatchResponse:
    filename, content = await _read_upload(request, settings.batch_max_file_bytes)

    def run() -> BatchResponse:
        parsed = parse_batch_csv(
            filename,
            content,
            max_file_bytes=settings.batch_max_file_bytes,
            max_rows=settings.batch_max_rows,
        )
        return service.predict(parsed)

    return await run_in_threadpool(run)  # CPU 密集（驗證與推論）不佔用事件迴圈


@router.get(
    "/predictions/batch/template",
    summary="下載批次範本 CSV",
    description=(
        "回傳含 UTF-8 BOM 的範本：表頭為 customerID＋19 個特徵欄，兩列範例"
        "（DEMO-HIGH 的 TotalCharges 留空示範估算、DEMO-LOW 的 TotalCharges=2100）。"
        "不依賴模型；直接上傳必定成功。"
    ),
    response_class=Response,
    responses={
        200: {
            "description": "範本 CSV",
            "content": {"text/csv": {"schema": {"type": "string"}}},
        }
    },
)
def download_batch_template() -> Response:
    return Response(
        content=build_template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{TEMPLATE_FILENAME}"'},
    )
