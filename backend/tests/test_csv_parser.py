"""CSV 解析與逐列驗證（design.md 6.5.5）：檢查順序、Excel 列號、錯誤碼。"""

import csv
import io
from collections.abc import Callable
from typing import Any

import pytest

from churn_api.errors import AppError, ErrorCode
from churn_api.services.csv_parser import (
    MAX_REPORTED_ERRORS,
    build_template_csv,
    parse_batch_csv,
)
from churn_core.schema import FEATURES, REQUIRED_FEATURES

LIMITS: dict[str, Any] = {"max_file_bytes": 5_242_880, "max_rows": 10_000}


def parse(content: bytes, filename: str | None = "data.csv", **overrides: Any) -> Any:
    return parse_batch_csv(filename, content, **{**LIMITS, **overrides})


def error_of(content: bytes, filename: str | None = "data.csv", **overrides: Any) -> AppError:
    with pytest.raises(AppError) as info:
        parse(content, filename, **overrides)
    return info.value


def test_template_round_trips_and_is_valid() -> None:
    """AC-6.1：範本直接上傳必定成功。"""
    template = build_template_csv()
    assert template.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    assert b"\r\n" in template
    parsed = parse(template, "churn_batch_template.csv")
    assert [r.customer_id for r in parsed.rows] == ["DEMO-HIGH", "DEMO-LOW"]
    assert [r.row for r in parsed.rows] == [2, 3]
    assert parsed.has_customer_id is True
    assert parsed.ignored_columns == []
    assert parsed.rows[0].features.TotalCharges is None  # 高風險範例留空 → 估算
    assert parsed.rows[1].features.TotalCharges == 2100.0
    header = next(csv.reader(io.StringIO(template.decode("utf-8-sig"))))
    assert header == ["customerID", *FEATURES]


def test_bom_crlf_lf_and_trimmed_header(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    rows = [{**record(), "customerID": "A"}]
    padded_columns = ["customerID", *[f" {c} " for c in FEATURES]]  # 表頭前後空白會被去除
    padded_rows = [{f" {k} ": v for k, v in rows[0].items()}]
    assert parse(make_csv(padded_rows, padded_columns, bom=True)).rows[0].features.tenure == 1
    assert parse(make_csv(rows, bom=True, eol="\n")).rows[0].customer_id == "A"
    assert parse(make_csv(rows, bom=False, eol="\r\n")).rows[0].customer_id == "A"


def test_excel_row_numbers_count_blank_lines(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    """列號與 Excel 一致（表頭＝1）；空白列略過但仍佔列號。"""
    data = make_csv([{"customerID": "a", **record()}, {}, {"customerID": "c", **record()}])
    parsed = parse(data)
    assert [(r.row, r.customer_id) for r in parsed.rows] == [(2, "a"), (4, "c")]


def test_headers_are_case_sensitive_and_extras_ignored(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    columns = [*REQUIRED_FEATURES, "note", "", "Extra", "note"]  # 重複與空白欄名只列一次／不列
    row = {**record(), "note": "x", "Extra": "y"}
    parsed = parse(make_csv([row], columns))
    assert parsed.ignored_columns == ["note", "Extra"]
    assert parsed.has_customer_id is False
    assert parsed.rows[0].customer_id is None

    wrong_case = [("Tenure" if c == "tenure" else c) for c in REQUIRED_FEATURES]
    error = error_of(make_csv([record()], wrong_case))
    assert error.code is ErrorCode.MISSING_COLUMNS
    assert [d.field for d in error.details] == ["tenure"]


def test_missing_total_charges_column_or_cells_are_estimated(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    """AC-6.13：TotalCharges 欄可整欄省略或個別留空。"""
    no_column = parse(make_csv([record()], list(REQUIRED_FEATURES)))
    assert no_column.rows[0].features.TotalCharges is None

    mixed = parse(
        make_csv([record(TotalCharges=500), record(TotalCharges=None), record(TotalCharges="  ")])
    )
    assert [r.features.TotalCharges for r in mixed.rows] == [500.0, None, None]


def test_customer_id_is_stripped_and_blank_becomes_none(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    data = make_csv([{**record(), "customerID": "  ID-1  "}, {**record(), "customerID": "  "}])
    assert [r.customer_id for r in parse(data).rows] == ["ID-1", None]


def test_cells_are_trimmed(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    row = record(gender="  Female ", tenure=" 12 ", MonthlyCharges=" 50.5 ")
    features = parse(make_csv([row])).rows[0].features
    assert (features.gender, features.tenure, features.MonthlyCharges) == ("Female", 12, 50.5)


@pytest.mark.parametrize(
    ("overrides", "field", "etype"),
    [
        ({"tenure": "10.0"}, "tenure", "invalid_type"),  # 整數須為整數字面值
        ({"tenure": "10.5"}, "tenure", "invalid_type"),
        ({"tenure": "abc"}, "tenure", "invalid_type"),
        ({"tenure": "1e1"}, "tenure", "invalid_type"),
        ({"tenure": "-1"}, "tenure", "out_of_range"),
        ({"tenure": "73"}, "tenure", "out_of_range"),
        ({"tenure": ""}, "tenure", "missing"),
        ({"gender": ""}, "gender", "missing"),
        ({"gender": "female"}, "gender", "invalid_choice"),
        ({"SeniorCitizen": "1.0"}, "SeniorCitizen", "invalid_type"),
        ({"SeniorCitizen": "true"}, "SeniorCitizen", "invalid_type"),
        ({"SeniorCitizen": "2"}, "SeniorCitizen", "invalid_choice"),
        ({"MonthlyCharges": "abc"}, "MonthlyCharges", "invalid_type"),
        ({"MonthlyCharges": "nan"}, "MonthlyCharges", "invalid_type"),
        ({"MonthlyCharges": "inf"}, "MonthlyCharges", "invalid_type"),
        ({"MonthlyCharges": "1_0"}, "MonthlyCharges", "invalid_type"),  # 不接受底線數字
        ({"MonthlyCharges": "200.5"}, "MonthlyCharges", "out_of_range"),
        ({"TotalCharges": "abc"}, "TotalCharges", "invalid_type"),
        ({"TotalCharges": "-5"}, "TotalCharges", "out_of_range"),
        ({"TotalCharges": "10001"}, "TotalCharges", "out_of_range"),
        ({"PhoneService": "No"}, "MultipleLines", "inconsistent"),
        ({"InternetService": "No"}, "OnlineSecurity", "inconsistent"),
    ],
)
def test_invalid_cells_reported_with_excel_row(
    record: Callable[..., dict[str, Any]],
    make_csv: Callable[..., bytes],
    overrides: dict[str, Any],
    field: str,
    etype: str,
) -> None:
    error = error_of(make_csv([record(), record(**overrides)]))
    assert error.code is ErrorCode.INVALID_ROWS
    assert error.status_code == 422
    matched = [d for d in error.details if d.field == field]
    assert matched
    assert matched[0].type == etype
    assert matched[0].row == 3  # 第二筆資料 = Excel 第 3 列
    assert error.meta is not None
    assert error.meta["invalid_row_count"] == 1


def test_estimate_over_limit_is_row_error_on_total_charges(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    error = error_of(make_csv([record(tenure=72, MonthlyCharges=200, TotalCharges=None)]))
    (detail,) = error.details
    assert (detail.field, detail.row, detail.type) == ("TotalCharges", 2, "out_of_range")
    assert detail.reason == "累計費用估算值為 14,400.00，超過上限 10,000，請手動填寫累計費用"


def test_details_capped_at_20_with_totals_and_ordering(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    """AC-6.7：只回前 20 筆（依列號、欄位順序），meta 帶總數。"""
    good = record()
    bad = record(tenure=-1, gender="x")  # 每列 2 個錯誤
    rows = [good, bad, good] + [bad] * 29  # 無效列：Excel 第 3 列與第 5 列起共 30 列
    error = error_of(make_csv(rows))
    assert error.code is ErrorCode.INVALID_ROWS
    assert len(error.details) == MAX_REPORTED_ERRORS == 20
    assert error.meta == {"total_errors": 60, "invalid_row_count": 30}
    row_numbers = [d.row for d in error.details if d.row is not None]
    assert row_numbers == sorted(row_numbers)
    first_row = [d for d in error.details if d.row == 3]
    assert [d.field for d in first_row] == ["gender", "tenure"]  # 欄位順序同 FEATURES
    assert error.details[0].row == 3
    assert error.details[-1].row == 13  # 無效列為 3、5、6…13，前 10 列共 20 筆


def test_short_rows_and_extra_cells(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    columns = ["customerID", *FEATURES]
    lines = make_csv([{**record(), "customerID": "ok"}], columns).decode().splitlines()
    short = ",".join(lines[1].split(",")[:6])  # 只有前 6 欄
    extra = lines[1] + ",surplus,cells"
    error = error_of(("\r\n".join([lines[0], short, extra]) + "\r\n").encode())
    assert error.code is ErrorCode.INVALID_ROWS
    assert {d.row for d in error.details} == {2}  # 多出的儲存格只是被忽略，短列才有錯
    assert all(d.type == "missing" for d in error.details)


def test_non_csv_and_undecodable_are_415(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    good = make_csv([record()])
    for name in ("data.txt", "data.csv.exe", "data", "data.xlsx", None):
        error = error_of(good, name)
        assert error.code is ErrorCode.UNSUPPORTED_FILE_TYPE
        assert error.status_code == 415
    assert parse(good, "DATA.CSV").rows  # 副檔名不分大小寫

    cp950 = make_csv([record(gender="女")]).decode("utf-8").encode("cp950")
    error = error_of(cp950)
    assert error.code is ErrorCode.UNSUPPORTED_FILE_TYPE
    assert "UTF-8" in error.message
    assert error_of(b"\xff\xfe\x00\x01garbage").code is ErrorCode.UNSUPPORTED_FILE_TYPE


def test_duplicate_known_columns_rejected(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    error = error_of(make_csv([record()], [*REQUIRED_FEATURES, "tenure"]))
    assert error.code is ErrorCode.UNSUPPORTED_FILE_TYPE
    assert "tenure" in error.message


@pytest.mark.parametrize("content", [b"", b"\xef\xbb\xbf", b"  \r\n\r\n ", b"\n\n"])
def test_empty_file_is_400(content: bytes) -> None:
    error = error_of(content)
    assert error.code is ErrorCode.FILE_EMPTY
    assert error.status_code == 400


def test_header_only_is_400(make_csv: Callable[..., bytes]) -> None:
    assert error_of(make_csv([])).code is ErrorCode.FILE_EMPTY
    assert error_of(make_csv([{}, {}])).code is ErrorCode.FILE_EMPTY  # 只有空白列


def test_missing_columns_listed(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    """AC-6.6：缺欄回 422 MISSING_COLUMNS，每個缺少欄一筆 details。"""
    columns = [c for c in REQUIRED_FEATURES if c not in ("tenure", "Contract")]
    error = error_of(make_csv([record()], columns))
    assert error.code is ErrorCode.MISSING_COLUMNS
    assert error.status_code == 422
    assert [(d.field, d.type, d.row) for d in error.details] == [
        ("tenure", "missing_column", None),
        ("Contract", "missing_column", None),
    ]
    assert "tenure" in error.message
    assert "Contract" in error.message


def test_size_and_row_limits(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    data = make_csv([record()] * 6)
    too_many = error_of(data, max_rows=5)
    assert too_many.code is ErrorCode.TOO_MANY_ROWS
    assert too_many.status_code == 413
    assert too_many.meta == {"max_rows": 5, "rows": 6}
    assert parse(data, max_rows=6).rows  # 剛好等於上限可通過

    too_large = error_of(data, max_file_bytes=len(data) - 1)
    assert too_large.code is ErrorCode.FILE_TOO_LARGE
    assert too_large.status_code == 413
    assert too_large.meta == {"max_file_bytes": len(data) - 1}
    assert parse(data, max_file_bytes=len(data)).rows


def test_check_order_size_ext_empty_rows_columns_then_rows_validation(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    assert error_of(b"x" * 100, "a.txt", max_file_bytes=10).code is ErrorCode.FILE_TOO_LARGE
    assert error_of(b"", "a.txt").code is ErrorCode.UNSUPPORTED_FILE_TYPE  # 副檔名先於空檔
    no_tenure = [c for c in REQUIRED_FEATURES if c != "tenure"]
    data = make_csv([record()] * 3, no_tenure)
    assert error_of(data, max_rows=2).code is ErrorCode.TOO_MANY_ROWS  # 列數先於缺欄
    assert error_of(data).code is ErrorCode.MISSING_COLUMNS
    assert error_of(make_csv([record(tenure=-1)])).code is ErrorCode.INVALID_ROWS


def test_quoted_cells_with_commas_and_newlines(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    rows = [{**record(), "customerID": "a,b\nc"}, {**record(), "customerID": "d"}]
    parsed = parse(make_csv(rows))
    assert [r.customer_id for r in parsed.rows] == ["a,b\nc", "d"]
    assert [r.row for r in parsed.rows] == [2, 3]  # 儲存格內換行不影響 Excel 列號


def test_is_deterministic(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    data = make_csv([record(tenure=t) for t in range(1, 30)])
    assert parse(data) == parse(data)


@pytest.mark.parametrize("name", ["tenure", "SeniorCitizen"])
def test_huge_integer_literal_is_422_not_500(
    record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes], name: str
) -> None:
    """超長數字（超過 int() 位數上限）必須回 422，不可拋未處理例外。"""
    error = error_of(make_csv([record(**{name: "9" * 5000})]))
    assert error.code is ErrorCode.INVALID_ROWS
    assert [d.field for d in error.details] == [name]
