"""批次 CSV 解析與逐列驗證（design.md 6.5.5、6.6）。

只處理記憶體中的位元組，不寫任何檔案、不記錄內容。檢查順序：
大小 → 副檔名／解碼／解析 → 空檔 → 列數 → 缺欄 → 逐列驗證；任一失敗即丟 `AppError`，不做任何預測。

每列以 `CustomerFeatures` 驗證（與單筆 API 同一個 Pydantic 模型）。儲存格值去除前後空白；
空白儲存格視為 missing（TotalCharges 除外，改為 None 由估算處理）。數值儲存格只在「整數／十進位數字
字面值」時才轉型：`tenure=10` 可、`10.0`／`10.5` 保持字串而被嚴格驗證擋下。
"""

import csv
import io
import math
import re
from dataclasses import dataclass
from typing import Any, Final

from pydantic import ValidationError

from churn_api.errors import AppError, ErrorCode, translate_pydantic_errors
from churn_api.schemas.common import ErrorDetail
from churn_api.schemas.prediction import CustomerFeatures
from churn_core.examples import HIGH_RISK_EXAMPLE, LOW_RISK_EXAMPLE
from churn_core.schema import FEATURES, ID_COLUMN, REQUIRED_FEATURES

MAX_REPORTED_ERRORS: Final = 20  # INVALID_ROWS 的 details 只回前 20 筆
_FEATURE_ORDER: Final = {name: index for index, name in enumerate(FEATURES)}
# 限制長度：避免超長數字觸發 int() 的位數上限而變成 500
_INT_PATTERN: Final = re.compile(r"[+-]?[0-9]{1,9}")
_NUMBER_PATTERN: Final = re.compile(r"[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?")
_INTEGER_FEATURES: Final = frozenset({"tenure", "SeniorCitizen"})
_FLOAT_FEATURES: Final = frozenset({"MonthlyCharges", "TotalCharges"})
TEMPLATE_FILENAME: Final = "churn_batch_template.csv"
TEMPLATE_CUSTOMER_IDS: Final = ("DEMO-HIGH", "DEMO-LOW")


@dataclass(frozen=True)
class ParsedRow:
    row: int  # Excel 列號
    customer_id: str | None
    features: CustomerFeatures


@dataclass(frozen=True)
class ParsedBatch:
    rows: list[ParsedRow]
    has_customer_id: bool
    ignored_columns: list[str]
    file_bytes: int


def _convert(name: str, cell: str) -> Any:
    """去除空白後依欄位轉型；無法照字面轉型的值原樣保留（交給嚴格驗證回報）。"""
    text = cell.strip()
    if name in _INTEGER_FEATURES and _INT_PATTERN.fullmatch(text):
        return int(text)
    if name in _FLOAT_FEATURES and _NUMBER_PATTERN.fullmatch(text):
        number = float(text)
        return number if math.isfinite(number) else text
    return text


def _decode(content: bytes, filename: str | None) -> str:
    if filename is None or not filename.lower().endswith(".csv"):
        raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE, message="僅支援副檔名為 .csv 的檔案。")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AppError(
            ErrorCode.UNSUPPORTED_FILE_TYPE,
            message="檔案無法以 UTF-8 解碼，請另存為 UTF-8 的 CSV。",
        ) from None


def _read_records(text: str) -> list[list[str]]:
    """讀出所有記錄（含空白記錄，供列號計算）；CSV 格式錯誤 → 415。"""
    try:
        return list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error:
        raise AppError(
            ErrorCode.UNSUPPORTED_FILE_TYPE, message="檔案無法解析為 CSV，請確認格式。"
        ) from None


def _is_blank(record: list[str]) -> bool:
    return all(not cell.strip() for cell in record)


def parse_batch_csv(
    filename: str | None,
    content: bytes,
    *,
    max_file_bytes: int,
    max_rows: int,
) -> ParsedBatch:
    """解析並驗證整份 CSV；任何錯誤都丟 `AppError`（對應 design.md 6.3 錯誤碼）。"""
    if len(content) > max_file_bytes:
        raise AppError(
            ErrorCode.FILE_TOO_LARGE,
            meta={"max_file_bytes": max_file_bytes},
        )
    text = _decode(content, filename)
    records = _read_records(text)

    if not records or _is_blank(records[0]):
        raise AppError(ErrorCode.FILE_EMPTY)
    header = [cell.strip() for cell in records[0]]
    # (Excel 列號, 儲存格)；空白列略過但仍佔列號
    data = [
        (index + 1, record)
        for index, record in enumerate(records[1:], start=1)
        if not _is_blank(record)
    ]
    if not data:
        raise AppError(ErrorCode.FILE_EMPTY)
    if len(data) > max_rows:
        raise AppError(
            ErrorCode.TOO_MANY_ROWS,
            meta={"max_rows": max_rows, "rows": len(data)},
        )

    known = set(FEATURES) | {ID_COLUMN}
    seen: set[str] = set()
    duplicated: list[str] = []
    for name in header:
        if name in known and name in seen and name not in duplicated:
            duplicated.append(name)
        seen.add(name)
    if duplicated:
        raise AppError(
            ErrorCode.UNSUPPORTED_FILE_TYPE,
            message=f"表頭欄位名稱重複：{'、'.join(duplicated)}",
        )

    missing = [name for name in REQUIRED_FEATURES if name not in seen]
    if missing:
        raise AppError(
            ErrorCode.MISSING_COLUMNS,
            message=f"檔案缺少必要欄位：{'、'.join(missing)}",
            details=[
                ErrorDetail(
                    field=name, row=None, type="missing_column", reason=f"缺少必要欄位：{name}"
                )
                for name in missing
            ],
        )

    ignored = list(dict.fromkeys(name for name in header if name and name not in known))
    positions = {name: index for index, name in enumerate(header) if name in known}
    has_customer_id = ID_COLUMN in positions

    parsed: list[ParsedRow] = []
    all_errors: list[ErrorDetail] = []
    invalid_rows = 0
    for row_number, cells in data:
        record: dict[str, Any] = {}
        for name in FEATURES:
            position = positions.get(name)
            if position is None:
                continue  # 只可能是 TotalCharges 欄整欄省略 → 由估算處理
            cell = cells[position] if position < len(cells) else ""
            if not cell.strip():
                if name == "TotalCharges":
                    record[name] = None
                continue  # 其餘空白 → 不放入，驗證時回報 missing
            record[name] = _convert(name, cell)
        try:
            features = CustomerFeatures.model_validate(record)
        except ValidationError as exc:
            invalid_rows += 1
            details = translate_pydantic_errors(exc.errors(), row=row_number)
            details.sort(key=lambda d: _FEATURE_ORDER.get(d.field or "", len(FEATURES)))
            all_errors.extend(details)
            continue
        customer_id: str | None = None
        if has_customer_id:
            position = positions[ID_COLUMN]
            raw_id = cells[position].strip() if position < len(cells) else ""
            customer_id = raw_id or None
        parsed.append(ParsedRow(row=row_number, customer_id=customer_id, features=features))

    if all_errors:
        raise AppError(
            ErrorCode.INVALID_ROWS,
            details=all_errors[:MAX_REPORTED_ERRORS],
            meta={"total_errors": len(all_errors), "invalid_row_count": invalid_rows},
        )
    return ParsedBatch(
        rows=parsed,
        has_customer_id=has_customer_id,
        ignored_columns=ignored,
        file_bytes=len(content),
    )


def build_template_csv() -> bytes:
    """範本 CSV（UTF-8 BOM、CRLF）：customerID＋19 欄，兩列範例（高風險省略 TotalCharges）。"""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([ID_COLUMN, *FEATURES])
    for customer_id, example in zip(
        TEMPLATE_CUSTOMER_IDS, (HIGH_RISK_EXAMPLE, LOW_RISK_EXAMPLE), strict=True
    ):
        writer.writerow([customer_id, *(example.get(name, "") for name in FEATURES)])
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")
