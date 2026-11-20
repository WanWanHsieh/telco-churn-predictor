"""錯誤處理：6.3 格式、錯誤碼總表、Pydantic 繁中翻譯、500 不洩漏（NFR-7）。"""

import io
import json
import re
from collections.abc import Callable
from typing import Any, Literal

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from churn_api.errors import (
    ERROR_SPECS,
    AppError,
    ErrorCode,
    error_responses,
    translate_pydantic_errors,
)
from churn_api.logging_config import configure_logging
from churn_api.main import create_app
from churn_api.schemas.common import ErrorDetail
from churn_api.settings import Settings
from churn_core.imputation import EstimateOverLimitError

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ERROR_KEYS = {"code", "message", "details", "meta", "request_id"}

# design.md 6.3 錯誤碼總表
EXPECTED_STATUS = {
    "FILE_EMPTY": 400,
    "METRICS_NOT_FOUND": 404,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "FILE_TOO_LARGE": 413,
    "TOO_MANY_ROWS": 413,
    "UNSUPPORTED_FILE_TYPE": 415,
    "VALIDATION_ERROR": 422,
    "MISSING_COLUMNS": 422,
    "INVALID_ROWS": 422,
    "INTERNAL_ERROR": 500,
    "MODEL_UNAVAILABLE": 503,
}


class Features(BaseModel):
    """測試用的精簡版 CustomerFeatures（嚴格型別、拒絕額外欄位、連動一致性）。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    gender: Literal["Female", "Male"]
    SeniorCitizen: Literal[0, 1]
    tenure: int = Field(ge=0, le=72)
    PhoneService: Literal["Yes", "No"]
    MultipleLines: Literal["Yes", "No", "No phone service"]
    MonthlyCharges: float = Field(ge=0, le=200)
    TotalCharges: float | None = Field(default=None, ge=0, le=10_000)

    @field_validator("MultipleLines")
    @classmethod
    def _consistent(cls, value: str, info: ValidationInfo) -> str:
        phone = info.data.get("PhoneService")
        if phone is not None and (phone == "No") != (value == "No phone service"):
            raise PydanticCustomError("inconsistent", "與 PhoneService 不一致")
        return value


VALID: dict[str, Any] = {
    "gender": "Female",
    "SeniorCitizen": 0,
    "tenure": 10,
    "PhoneService": "Yes",
    "MultipleLines": "No",
    "MonthlyCharges": 50.0,
}


@pytest.fixture
def client(
    make_client: Callable[..., TestClient], make_settings: Callable[..., Settings]
) -> TestClient:
    app: FastAPI = create_app(make_settings())

    @app.post("/echo")
    def echo(body: Features) -> dict[str, int]:
        return {"tenure": body.tenure}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret C:\\internal\\path\\db.sqlite password=hunter2")

    @app.get("/raise/{code}")
    def raise_code(code: str) -> None:
        raise AppError(ErrorCode(code))

    @app.get("/http/{status}")
    def raise_http(status: int) -> None:
        raise HTTPException(status_code=status, detail="framework detail should not leak")

    return make_client(app)


def _error(response: Any) -> dict[str, Any]:
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == ERROR_KEYS
    assert isinstance(body["error"]["details"], list)
    assert response.headers["x-request-id"] == body["error"]["request_id"]
    error: dict[str, Any] = body["error"]
    return error


def test_error_spec_table_matches_design() -> None:
    assert {code.value: spec.status for code, spec in ERROR_SPECS.items()} == EXPECTED_STATUS
    assert set(ErrorCode) == set(ERROR_SPECS)
    for spec in ERROR_SPECS.values():
        assert spec.message  # 皆為預設繁中訊息


@pytest.mark.parametrize("code", sorted(EXPECTED_STATUS))
def test_every_error_code_renders_unified_format(client: TestClient, code: str) -> None:
    response = client.get(f"/raise/{code}")
    assert response.status_code == EXPECTED_STATUS[code]
    error = _error(response)
    assert error["code"] == code
    assert error["message"] == ERROR_SPECS[ErrorCode(code)].message
    assert error["details"] == []
    assert error["meta"] is None


def test_exact_messages_from_design(client: TestClient) -> None:
    assert (
        _error(client.get("/raise/MODEL_UNAVAILABLE"))["message"]
        == "模型尚未載入，服務暫時無法使用。"
    )
    assert (
        _error(client.get("/raise/VALIDATION_ERROR"))["message"]
        == "輸入資料有誤，請檢查標示的欄位。"
    )


def test_not_found_and_method_not_allowed(client: TestClient) -> None:
    missing = client.get("/no/such/path")
    assert missing.status_code == 404
    assert _error(missing)["code"] == "NOT_FOUND"

    wrong_method = client.get("/echo")
    assert wrong_method.status_code == 405
    assert _error(wrong_method)["code"] == "METHOD_NOT_ALLOWED"
    assert "POST" in wrong_method.headers["allow"]


def test_other_http_exceptions_do_not_leak_framework_detail(client: TestClient) -> None:
    bad = client.get("/http/400")
    assert bad.status_code == 422
    assert _error(bad)["code"] == "VALIDATION_ERROR"
    assert "framework detail" not in bad.text

    upstream = client.get("/http/502")
    assert upstream.status_code == 500
    assert _error(upstream)["code"] == "INTERNAL_ERROR"
    assert "framework detail" not in upstream.text


def test_app_error_carries_details_and_meta(
    make_client: Callable[..., TestClient], make_settings: Callable[..., Settings]
) -> None:
    app = create_app(make_settings())

    @app.get("/invalid-rows")
    def invalid_rows() -> None:
        raise AppError(
            ErrorCode.INVALID_ROWS,
            details=[ErrorDetail(field="tenure", row=3, type="out_of_range", reason="需為整數")],
            meta={"total_errors": 57, "invalid_row_count": 31},
        )

    response = make_client(app).get("/invalid-rows")
    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "INVALID_ROWS"
    assert error["details"] == [
        {"field": "tenure", "row": 3, "type": "out_of_range", "reason": "需為整數"}
    ]
    assert error["meta"] == {"total_errors": 57, "invalid_row_count": 31}


def test_service_supplied_reason_for_estimate_over_limit(
    make_client: Callable[..., TestClient], make_settings: Callable[..., Settings]
) -> None:
    """service 可把 EstimateOverLimitError 的 field／type／reason 帶入 details，不需新錯誤碼。"""
    app = create_app(make_settings())

    @app.get("/over-limit")
    def over_limit() -> None:
        exc = EstimateOverLimitError(14_400.0)
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            details=[
                ErrorDetail(field=exc.field, row=None, type="out_of_range", reason=exc.reason)
            ],
        )

    response = make_client(app).get("/over-limit")
    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"] == [
        {
            "field": "TotalCharges",
            "row": None,
            "type": "out_of_range",
            "reason": "累計費用估算值為 14,400.00，超過上限 10,000，請手動填寫累計費用",
        }
    ]


def test_valid_body_passes(client: TestClient) -> None:
    response = client.post("/echo", json=VALID)
    assert response.status_code == 200
    assert response.json() == {"tenure": 10}


@pytest.mark.parametrize(
    ("patch", "field", "etype", "reason"),
    [
        ({"tenure": 73}, "tenure", "out_of_range", "在網月數需為 0 至 72 的整數"),
        ({"tenure": -1}, "tenure", "out_of_range", "在網月數需為 0 至 72 的整數"),
        ({"tenure": 10.5}, "tenure", "invalid_type", "在網月數需為 0 至 72 的整數"),
        ({"tenure": "10"}, "tenure", "invalid_type", "在網月數需為 0 至 72 的整數"),
        ({"MonthlyCharges": 201}, "MonthlyCharges", "out_of_range", "月費需介於 0 至 200 之間"),
        ({"MonthlyCharges": "50"}, "MonthlyCharges", "invalid_type", "月費需介於 0 至 200 之間"),
        ({"TotalCharges": -5}, "TotalCharges", "out_of_range", "累計費用需為 0 以上的數字"),
        ({"TotalCharges": "abc"}, "TotalCharges", "invalid_type", "累計費用需為 0 以上的數字"),
        ({"TotalCharges": 10_001}, "TotalCharges", "out_of_range", "累計費用不可超過 10,000"),
        ({"gender": "female"}, "gender", "invalid_choice", "不是合法選項，可用值：Female、Male"),
        ({"gender": 1}, "gender", "invalid_choice", "不是合法選項，可用值：Female、Male"),
        ({"SeniorCitizen": 2}, "SeniorCitizen", "invalid_choice", "是否為年長者需為整數 0 或 1"),
        ({"SeniorCitizen": "0"}, "SeniorCitizen", "invalid_choice", "是否為年長者需為整數 0 或 1"),
        ({"Typo": 1}, "Typo", "extra_field", "不認識的欄位，請檢查欄位名稱是否拼錯"),
        (
            {"PhoneService": "No"},
            "MultipleLines",
            "inconsistent",
            "與 PhoneService 不一致",
        ),
    ],
)
def test_validation_error_translation(
    client: TestClient, patch: dict[str, Any], field: str, etype: str, reason: str
) -> None:
    response = client.post("/echo", json={**VALID, **patch})
    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert {"field": field, "row": None, "type": etype, "reason": reason} in error["details"]
    # 回應不含使用者輸入值與英文框架訊息
    assert "Input should" not in response.text
    assert "input" not in {k for d in error["details"] for k in d}


def test_missing_field_and_all_errors_listed(client: TestClient) -> None:
    body = {k: v for k, v in VALID.items() if k != "gender"}
    body["tenure"] = 999
    body["MonthlyCharges"] = "x"
    body["Typo"] = 1
    error = _error(client.post("/echo", json=body))
    by_field = {d["field"]: d for d in error["details"]}
    assert set(by_field) == {"gender", "tenure", "MonthlyCharges", "Typo"}  # 不只第一個
    assert by_field["gender"]["type"] == "missing"
    assert by_field["gender"]["reason"] == "缺少必填欄位：性別"


def test_invalid_json_body(client: TestClient) -> None:
    response = client.post(
        "/echo", content="{bad json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"] == [
        {"field": None, "row": None, "type": "invalid_type", "reason": "請求內容不是有效的 JSON"}
    ]


def test_non_object_body(client: TestClient) -> None:
    response = client.post("/echo", json=[1, 2, 3])
    assert response.status_code == 422
    assert _error(response)["details"][0]["reason"] == "請求內容需為 JSON 物件"


def test_translate_supports_batch_row_and_custom_types() -> None:
    errors: list[dict[str, Any]] = [
        {"type": "int_type", "loc": ("tenure",), "msg": "x", "input": 1},
        {"type": "out_of_range", "loc": ("TotalCharges",), "msg": "累計費用估算值超過上限"},
        {"type": "inconsistent", "loc": ("MultipleLines",), "msg": "與 PhoneService 不一致"},
        {"type": "value_error", "loc": (), "msg": "Value error, x", "ctx": {"error": "自訂說明"}},
        {"type": "something_new", "loc": ("body", "foo"), "msg": "english"},
        {"type": "greater_than", "loc": ("unknown_numeric",), "msg": "x"},
        {"type": "string_type", "loc": ("gender",), "msg": "x"},
        {"type": "int_type", "loc": ("SeniorCitizen",), "msg": "x"},
    ]
    details = translate_pydantic_errors(errors, row=7)
    assert [d.row for d in details] == [7] * len(errors)
    assert [(d.field, d.type, d.reason) for d in details] == [
        ("tenure", "invalid_type", "在網月數需為 0 至 72 的整數"),
        ("TotalCharges", "out_of_range", "累計費用估算值超過上限"),
        ("MultipleLines", "inconsistent", "與 PhoneService 不一致"),
        (None, "inconsistent", "自訂說明"),
        ("foo", "invalid_type", "格式不正確"),
        ("unknown_numeric", "out_of_range", "數值超出允許範圍"),
        ("gender", "invalid_type", "型別錯誤，需為文字，可用值：Female、Male"),
        ("SeniorCitizen", "invalid_type", "是否為年長者需為整數 0 或 1"),
    ]


def test_unhandled_exception_returns_500_without_leaking(
    client: TestClient, make_settings: Callable[..., Settings]
) -> None:
    stream = io.StringIO()
    configure_logging("INFO", "production", stream=stream)
    try:
        response = client.get("/boom", headers={"X-Request-ID": "rid-500"})
    finally:
        configure_logging("INFO", "production")

    assert response.status_code == 500
    error = _error(response)
    assert error["code"] == "INTERNAL_ERROR"
    assert error["message"] == ERROR_SPECS[ErrorCode.INTERNAL_ERROR].message
    assert error["request_id"] == "rid-500"
    for leaked in ("hunter2", "internal", "Traceback", "RuntimeError", "secret", ".py"):
        assert leaked not in response.text

    log_text = stream.getvalue()
    assert "RuntimeError" in log_text  # 堆疊只進 log
    assert "hunter2" in log_text
    assert "unhandled_exception" in log_text


def test_request_id_header_rules(client: TestClient) -> None:
    kept = client.get("/no/such", headers={"X-Request-ID": "abc-123_X.y"})
    assert kept.headers["x-request-id"] == "abc-123_X.y"
    assert kept.json()["error"]["request_id"] == "abc-123_X.y"

    for bad in ("has space", "x" * 65, "a;b"):
        replaced = client.get("/no/such", headers={"X-Request-ID": bad})
        assert replaced.headers["x-request-id"] != bad
        assert UUID_RE.match(replaced.headers["x-request-id"])

    generated = client.get("/no/such")
    assert UUID_RE.match(generated.headers["x-request-id"])


def test_error_responses_helper_documents_models_and_examples() -> None:
    docs = error_responses(
        ErrorCode.MODEL_UNAVAILABLE, ErrorCode.FILE_EMPTY, ErrorCode.VALIDATION_ERROR
    )
    assert set(docs) == {503, 400, 422}
    example = docs[503]["content"]["application/json"]["examples"]["MODEL_UNAVAILABLE"]["value"]
    assert set(example["error"]) == ERROR_KEYS


def test_cross_origin_unhandled_exception_has_cors_and_path_logged(
    make_client: Callable[..., TestClient], make_settings: Callable[..., Settings]
) -> None:
    app = create_app(make_settings(cors_allow_origins="http://localhost:8080"))

    @app.get("/boom2")
    def boom2() -> None:
        raise RuntimeError("secret")

    stream = io.StringIO()
    configure_logging("INFO", "production", stream=stream)
    try:
        client = make_client(app)
        ok = client.get("/boom2", headers={"Origin": "http://localhost:8080"})
        bad = client.get("/boom2", headers={"Origin": "http://evil.example.com"})
    finally:
        configure_logging("INFO", "production")

    assert ok.status_code == 500
    assert ok.headers["access-control-allow-origin"] == "http://localhost:8080"
    assert _error(ok)["code"] == "INTERNAL_ERROR"
    assert bad.status_code == 500
    assert "access-control-allow-origin" not in bad.headers  # 同一白名單
    assert "secret" not in ok.text

    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    crashes = [e for e in events if e["event"] == "unhandled_exception"]
    assert [e["path"] for e in crashes] == ["/boom2", "/boom2"]
    assert all(e["method"] == "GET" for e in crashes)
    access = [e for e in events if e["event"] == "http_request" and e["path"] == "/boom2"]
    assert [e["status"] for e in access] == [500, 500]
