"""JSON log：一行一 JSON、欄位齊全、不含請求本體（design.md 第 8 節、NFR-8）。"""

import io
import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from churn_api.logging_config import configure_logging, log_event, request_id_var
from churn_api.main import create_app
from churn_api.settings import Settings


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    buffer = io.StringIO()
    configure_logging("INFO", "production", stream=buffer)
    yield buffer
    configure_logging("INFO", "production")  # 還原為 stdout handler


def _lines(buffer: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in buffer.getvalue().splitlines() if line]


def test_each_line_is_one_json_with_required_fields(stream: io.StringIO) -> None:
    token = request_id_var.set("rid-1")
    try:
        log_event(logging.getLogger("churn_api.test"), logging.INFO, "demo", "第一行\n第二行", n=3)
    finally:
        request_id_var.reset(token)
    (record,) = _lines(stream)
    assert stream.getvalue().count("\n") == 1  # 訊息內的換行被跳脫，仍是單行
    assert record["event"] == "demo"
    assert record["level"] == "INFO"
    assert record["logger"] == "churn_api.test"
    assert record["request_id"] == "rid-1"
    assert record["n"] == 3
    assert record["message"] == "第一行\n第二行"
    assert record["ts"].endswith("Z")


def test_exception_stack_goes_to_log_only(stream: io.StringIO) -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        log_event(logging.getLogger("churn_api.test"), logging.ERROR, "failed", exc_info=exc)
    (record,) = _lines(stream)
    assert "RuntimeError: boom" in record["exc_info"]


def test_development_format_is_human_readable() -> None:
    buffer = io.StringIO()
    configure_logging("INFO", "development", stream=buffer)
    try:
        log_event(logging.getLogger("churn_api.test"), logging.INFO, "demo", "hello", n=1)
    finally:
        configure_logging("INFO", "production")
    text = buffer.getvalue()
    assert "demo" in text
    assert "hello" in text
    assert "n=1" in text
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)


def test_reconfigure_does_not_duplicate_handlers(stream: io.StringIO) -> None:
    configure_logging("INFO", "production", stream=stream)
    configure_logging("INFO", "production", stream=stream)
    log_event(logging.getLogger("churn_api.test"), logging.INFO, "once")
    assert len(_lines(stream)) == 1


def test_default_handler_writes_json_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "production")
    log_event(logging.getLogger("churn_api.test"), logging.INFO, "to_stdout")
    record = json.loads(capsys.readouterr().out.strip())
    assert record["event"] == "to_stdout"


def test_access_log_has_no_body_or_query(
    stream: io.StringIO,
    make_client: Callable[..., TestClient],
    make_settings: Callable[..., Settings],
    artifact_dir: Path,
) -> None:
    app = create_app(make_settings(model_dir=artifact_dir))
    configure_logging(
        "INFO", "production", stream=stream
    )  # create_app 會重設 log，這裡改回測試串流
    client = make_client(app)
    secret = "SUPER-SECRET-VALUE"  # noqa: S105
    response = client.post(
        "/api/v1/health?token=" + secret,
        content=json.dumps({"tenure": secret}),
        headers={"X-Request-ID": "req-abc-123"},
    )
    assert response.status_code == 405
    assert secret not in stream.getvalue()
    access = [r for r in _lines(stream) if r["event"] == "http_request"]
    assert access, "應有存取 log"
    last = access[-1]
    assert last["method"] == "POST"
    assert last["path"] == "/api/v1/health"
    assert last["status"] == 405
    assert last["request_id"] == "req-abc-123"
    assert isinstance(last["duration_ms"], int | float)
    assert "client" in last


def test_validation_failed_logs_field_names_not_values(
    stream: io.StringIO,
    make_client: Callable[..., TestClient],
    make_settings: Callable[..., Settings],
    artifact_dir: Path,
) -> None:
    class Body(BaseModel):
        model_config = ConfigDict(extra="forbid")
        tenure: int

    app: FastAPI = create_app(make_settings(model_dir=artifact_dir))
    configure_logging("INFO", "production", stream=stream)

    @app.post("/echo")
    def echo(body: Body) -> dict[str, int]:
        return {"tenure": body.tenure}

    client = make_client(app)
    secret = "PRIVATE-INPUT"  # noqa: S105
    response = client.post("/echo", json={"tenure": secret})
    assert response.status_code == 422
    assert secret not in stream.getvalue()
    events = [r for r in _lines(stream) if r["event"] == "validation_failed"]
    assert events
    assert events[-1]["fields"] == ["tenure"]
