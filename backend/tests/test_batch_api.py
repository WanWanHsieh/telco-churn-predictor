"""POST /api/v1/predictions/batch 與 GET /api/v1/predictions/batch/template。"""

import asyncio
import io
import json
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from churn_api.api.v1.batch import _read_upload
from churn_api.errors import AppError, ErrorCode
from churn_api.logging_config import configure_logging
from churn_api.main import create_app
from churn_api.settings import Settings
from churn_core.examples import HIGH_RISK_EXAMPLE, LOW_RISK_EXAMPLE
from churn_core.schema import FEATURES

URL = "/api/v1/predictions/batch"
TEMPLATE_URL = "/api/v1/predictions/batch/template"
ERROR_KEYS = {"code", "message", "details", "meta", "request_id"}


@pytest.fixture
def client(make_client: Callable[..., TestClient], artifact_dir: Path) -> TestClient:
    return make_client(model_dir=artifact_dir)


def upload(client: TestClient, content: bytes, filename: str = "data.csv", **kwargs: Any) -> Any:
    return client.post(URL, files={"file": (filename, content, "text/csv")}, **kwargs)


def error_of(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    error: dict[str, Any] = response.json()["error"]
    assert set(error) == ERROR_KEYS
    assert error["code"] == code
    assert error["request_id"] == response.headers["x-request-id"]
    return error


# ------------------------------------------------------------------ 範本
def test_template_download_and_direct_upload_succeeds(client: TestClient) -> None:
    """AC-6.1：範本含 BOM、表頭＋2 列，直接上傳回 200。"""
    response = client.get(TEMPLATE_URL)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert (
        response.headers["content-disposition"] == 'attachment; filename="churn_batch_template.csv"'
    )
    content = response.content
    assert content.startswith(b"\xef\xbb\xbf")
    lines = content.decode("utf-8-sig").splitlines()
    assert lines[0] == ",".join(["customerID", *FEATURES])
    assert len(lines) == 3
    assert lines[1].startswith("DEMO-HIGH,")
    assert lines[2].startswith("DEMO-LOW,")

    result = upload(client, content, "churn_batch_template.csv")
    assert result.status_code == 200
    body = result.json()
    assert [r["customer_id"] for r in body["results"]] == ["DEMO-HIGH", "DEMO-LOW"]
    assert [r["total_charges_estimated"] for r in body["results"]] == [True, False]


def test_template_does_not_depend_on_model(
    make_client: Callable[..., TestClient], tmp_path: Path
) -> None:
    assert make_client(model_dir=tmp_path / "none").get(TEMPLATE_URL).status_code == 200


# ------------------------------------------------------------------ 成功
def _rows(record: Callable[..., dict[str, Any]], count: int) -> list[dict[str, Any]]:
    base = [dict(HIGH_RISK_EXAMPLE), dict(LOW_RISK_EXAMPLE)]
    rows = []
    for i in range(count):
        row = dict(base[i % 2])
        row["tenure"] = 1 + (i * 7) % 72
        row["MonthlyCharges"] = round(20 + (i * 13) % 100 + 0.25, 2)
        row["customerID"] = f"CUST-{i:05d}"
        if i % 3 == 0:
            row.pop("TotalCharges", None)
        else:
            row["TotalCharges"] = round(row["tenure"] * row["MonthlyCharges"], 2)
        rows.append(row)
    return rows


def test_hundred_rows_structure_order_and_summary(
    client: TestClient, record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    """AC-6.2、6.5：design.md 6.5.5 結構；results 依原始順序；摘要正確。"""
    response = upload(client, make_csv(_rows(record, 100)))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "summary",
        "risk_thresholds",
        "model",
        "has_customer_id",
        "ignored_columns",
        "results",
    }
    results = body["results"]
    assert [r["row"] for r in results] == list(range(2, 102))
    assert [r["customer_id"] for r in results] == [f"CUST-{i:05d}" for i in range(100)]
    assert set(results[0]) == {
        "row",
        "customer_id",
        "probability",
        "risk_level",
        "total_charges_estimated",
        "input",
    }
    assert set(results[0]["input"]) == set(FEATURES)
    summary = body["summary"]
    levels = [r["risk_level"] for r in results]
    assert summary["total"] == 100
    assert (summary["high"], summary["medium"], summary["low"]) == (
        levels.count("high"),
        levels.count("medium"),
        levels.count("low"),
    )
    assert summary["high"] + summary["medium"] + summary["low"] == 100
    assert summary["estimated_total_charges"] == sum(r["total_charges_estimated"] for r in results)
    assert summary["estimated_total_charges"] == 34  # i % 3 == 0 的列
    assert body["has_customer_id"] is True
    assert body["ignored_columns"] == []
    assert body["risk_thresholds"] == {"medium": 0.3, "high": 0.6}
    assert body["model"]["name"] == "keras_mlp"
    assert all(r["probability"] == round(r["probability"], 3) for r in results)
    # input 中 TotalCharges 為原始值：估算列為 null
    assert results[0]["input"]["TotalCharges"] is None
    assert results[1]["input"]["TotalCharges"] is not None


def test_same_file_twice_gives_identical_results(
    client: TestClient, record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    """AC-6.12。"""
    data = make_csv(_rows(record, 60))
    assert upload(client, data).json() == upload(client, data).json()


def test_batch_matches_single_prediction(
    client: TestClient, record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    rows = _rows(record, 6)
    batch = upload(client, make_csv(rows)).json()["results"]
    for row, result in zip(rows, batch, strict=True):
        payload = {k: v for k, v in row.items() if k != "customerID"}
        single = client.post("/api/v1/predictions", json=payload).json()
        assert single["probability"] == result["probability"]
        assert single["risk_level"] == result["risk_level"]


def test_total_charges_column_missing_or_blank_is_estimated(
    client: TestClient, record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    """AC-6.13：無 TotalCharges 欄或部分空白可預測，旗標與摘要正確，且與手填估算值結果相同。"""
    base = record(tenure=10, MonthlyCharges=50.0)
    no_column = upload(client, make_csv([base], [c for c in FEATURES if c != "TotalCharges"]))
    assert no_column.status_code == 200
    assert no_column.json()["results"][0]["total_charges_estimated"] is True

    rows = [{**base, "TotalCharges": None}, {**base, "TotalCharges": 500}, {**base}]
    body = upload(client, make_csv(rows)).json()
    assert [r["total_charges_estimated"] for r in body["results"]] == [True, False, True]
    assert body["summary"]["estimated_total_charges"] == 2
    probabilities = {r["probability"] for r in body["results"]}
    assert len(probabilities) == 1  # 估算 500 與手填 500 預測相同


def test_extra_columns_ignored_and_listed(
    client: TestClient, record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    row = {**record(), "notes": "hello", "Region": "N"}
    body = upload(client, make_csv([row], [*FEATURES, "notes", "Region"])).json()
    assert body["ignored_columns"] == ["notes", "Region"]
    assert body["has_customer_id"] is False
    assert body["results"][0]["customer_id"] is None


def test_thousand_rows_within_ten_seconds(
    client: TestClient, record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    """AC-6.9 初驗（fixture 模型）：1,000 筆 < 10 秒。"""
    data = make_csv(_rows(record, 1000))
    upload(client, make_csv(_rows(record, 5)))  # 暖機
    started = time.perf_counter()
    response = upload(client, data)
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert response.json()["summary"]["total"] == 1000
    assert elapsed < 10
    print(f"\n[perf] 批次 1000 筆（fixture 模型，含 TestClient 開銷）：{elapsed * 1000:.0f} ms")


# ------------------------------------------------------------------ 錯誤碼
def test_non_csv_extension_and_bad_encoding_are_415(
    client: TestClient, record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    good = make_csv([record()])
    for name in ("data.txt", "data.xlsx", "data"):
        error_of(upload(client, good, name), 415, "UNSUPPORTED_FILE_TYPE")
    cp950 = make_csv([record(gender="女")]).decode().encode("cp950")
    error = error_of(upload(client, cp950), 415, "UNSUPPORTED_FILE_TYPE")
    assert "UTF-8" in error["message"]


def test_empty_and_header_only_are_400(client: TestClient, make_csv: Callable[..., bytes]) -> None:
    error_of(upload(client, b""), 400, "FILE_EMPTY")
    error_of(upload(client, make_csv([])), 400, "FILE_EMPTY")


def test_missing_columns_422_lists_names(
    client: TestClient, record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    """AC-6.6：缺少欄位：Contract、tenure。"""
    columns = [c for c in FEATURES if c not in ("tenure", "Contract")]
    error = error_of(upload(client, make_csv([record()], columns)), 422, "MISSING_COLUMNS")
    assert [d["field"] for d in error["details"]] == ["tenure", "Contract"]
    assert all(d["type"] == "missing_column" and d["row"] is None for d in error["details"])


def test_invalid_rows_422_whole_file_rejected(
    client: TestClient, record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    """AC-6.7：部分列非法整份拒絕；details ≤ 20；meta.total_errors；Excel 列號。"""
    rows = [record(), record(tenure=-1), *[record(tenure=999) for _ in range(30)]]
    error = error_of(upload(client, make_csv(rows)), 422, "INVALID_ROWS")
    assert len(error["details"]) == 20
    assert error["meta"] == {"total_errors": 31, "invalid_row_count": 31}
    assert error["details"][0] == {
        "field": "tenure",
        "row": 3,
        "type": "out_of_range",
        "reason": "在網月數需為 0 至 72 的整數",
    }
    assert [d["row"] for d in error["details"]] == list(range(3, 23))


def test_estimate_over_limit_row_is_invalid(
    client: TestClient, record: Callable[..., dict[str, Any]], make_csv: Callable[..., bytes]
) -> None:
    rows = [record(), record(tenure=72, MonthlyCharges=200.0)]
    error = error_of(upload(client, make_csv(rows)), 422, "INVALID_ROWS")
    assert error["details"] == [
        {
            "field": "TotalCharges",
            "row": 3,
            "type": "out_of_range",
            "reason": "累計費用估算值為 14,400.00，超過上限 10,000，請手動填寫累計費用",
        }
    ]


def test_too_many_rows_413(
    make_client: Callable[..., TestClient],
    artifact_dir: Path,
    record: Callable[..., dict[str, Any]],
    make_csv: Callable[..., bytes],
) -> None:
    client = make_client(model_dir=artifact_dir, batch_max_rows=5)
    error = error_of(upload(client, make_csv([record()] * 6)), 413, "TOO_MANY_ROWS")
    assert error["meta"] == {"max_rows": 5, "rows": 6}
    assert upload(client, make_csv([record()] * 5)).status_code == 200


def test_file_too_large_413_by_declared_length_and_by_content(
    make_client: Callable[..., TestClient],
    artifact_dir: Path,
    record: Callable[..., dict[str, Any]],
    make_csv: Callable[..., bytes],
) -> None:
    client = make_client(model_dir=artifact_dir, batch_max_file_bytes=2000)
    huge = b"x" * (2000 + 64 * 1024 + 10)  # 超過上限加上 multipart 額外空間：只看標頭就拒絕
    error = error_of(upload(client, huge), 413, "FILE_TOO_LARGE")
    assert error["meta"] == {"max_file_bytes": 2000}

    just_over = make_csv([record()] * 30)  # 在額外空間內、但檔案本身超過 2000 位元組
    assert 2000 < len(just_over) < 2000 + 64 * 1024
    error_of(upload(client, just_over), 413, "FILE_TOO_LARGE")


def test_not_multipart_or_missing_file_field_is_422(client: TestClient) -> None:
    error = error_of(client.post(URL, json={"a": 1}), 422, "VALIDATION_ERROR")
    assert error["details"][0]["field"] == "file"
    response = client.post(URL, files={"other": ("a.csv", b"x", "text/csv")})
    error = error_of(response, 422, "VALIDATION_ERROR")
    assert error["details"][0]["field"] == "file"
    text_field = client.post(URL, data={"file": "not a file"})
    error_of(text_field, 422, "VALIDATION_ERROR")


def test_model_unavailable_503(
    make_client: Callable[..., TestClient],
    tmp_path: Path,
    record: Callable[..., dict[str, Any]],
    make_csv: Callable[..., bytes],
) -> None:
    client = make_client(model_dir=tmp_path / "missing")
    error_of(upload(client, make_csv([record()])), 503, "MODEL_UNAVAILABLE")


# ------------------------------------------------------------------ 串流、隱私
def _fake_request(chunks: list[bytes], headers: dict[str, str]) -> tuple[Request, list[int]]:
    consumed: list[int] = []
    queue = list(chunks)

    async def receive() -> dict[str, Any]:
        consumed.append(1)
        body = queue.pop(0) if queue else b""
        return {"type": "http.request", "body": body, "more_body": bool(queue)}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/x",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope, receive), consumed


def test_oversized_stream_is_aborted_without_reading_everything() -> None:
    """AC-6.8：沒有 Content-Length（chunked）也會在超過上限時立即中止，不讀完整份。"""
    header = (
        b'--BOUNDARY\r\nContent-Disposition: form-data; name="file"; filename="a.csv"\r\n'
        b"Content-Type: text/csv\r\n\r\n"
    )
    chunks = [header] + [b"x" * 16_384 for _ in range(200)]  # 共約 3.2 MB
    request, consumed = _fake_request(
        chunks, {"content-type": "multipart/form-data; boundary=BOUNDARY"}
    )
    with pytest.raises(AppError) as info:
        asyncio.run(_read_upload(request, max_file_bytes=1000))
    assert info.value.code is ErrorCode.FILE_TOO_LARGE
    assert info.value.meta == {"max_file_bytes": 1000}
    assert len(consumed) < 20  # 上限約 66 KB ≈ 5 塊；遠少於 200 塊


def test_declared_content_length_over_limit_reads_nothing() -> None:
    request, consumed = _fake_request(
        [b"x"], {"content-type": "multipart/form-data; boundary=B", "content-length": "99999999"}
    )
    with pytest.raises(AppError) as info:
        asyncio.run(_read_upload(request, max_file_bytes=1000))
    assert info.value.code is ErrorCode.FILE_TOO_LARGE
    assert consumed == []


def test_no_leftover_temp_files_after_large_upload(
    make_client: Callable[..., TestClient],
    artifact_dir: Path,
    record: Callable[..., dict[str, Any]],
    make_csv: Callable[..., bytes],
) -> None:
    """AC-6.11：> 1 MB 的上傳會被 Starlette 暫存，處理後暫存目錄不得殘留檔案。"""
    client = make_client(model_dir=artifact_dir)
    rows = [{**r, "padding": "p" * 300} for r in _rows(record, 4000)]
    data = make_csv(rows, ["customerID", *FEATURES, "padding"])
    assert len(data) > 1_100_000
    temp_dir = Path(tempfile.gettempdir())
    before = set(os.listdir(temp_dir))
    response = upload(client, data)
    assert response.status_code == 200
    after = set(os.listdir(temp_dir))
    assert after - before == set()


def test_logs_never_contain_uploaded_content(
    make_settings: Callable[..., Settings],
    make_client: Callable[..., TestClient],
    artifact_dir: Path,
    record: Callable[..., dict[str, Any]],
    make_csv: Callable[..., bytes],
) -> None:
    """AC-6.11：log 只記列數、大小、處理時間，不含內容。"""
    stream = io.StringIO()
    app = create_app(make_settings(model_dir=artifact_dir))
    configure_logging("INFO", "production", stream=stream)
    client = make_client(app)
    secret = "SECRET-CUSTOMER-ID-12345"  # noqa: S105
    rows = [{**record(), "customerID": secret}, {**record(tenure=-1), "customerID": "BAD-ROW-ID"}]
    upload(client, make_csv(rows[:1]))
    upload(client, make_csv(rows))  # 失敗的上傳也不得記錄內容
    text = stream.getvalue()
    assert secret not in text
    assert "BAD-ROW-ID" not in text
    assert "Fiber optic" not in text
    events = [json.loads(line) for line in text.splitlines()]
    batch_events = [e for e in events if e["event"] == "batch_prediction"]
    assert len(batch_events) == 1
    assert batch_events[0]["rows"] == 1
    assert batch_events[0]["file_bytes"] > 0
    assert "duration_ms" in batch_events[0]
