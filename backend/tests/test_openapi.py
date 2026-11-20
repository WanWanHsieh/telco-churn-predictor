"""OpenAPI／Swagger：每支 API 有說明與請求／回應／錯誤範例（AC-5.2）、契約檔與程式一致。"""

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "backend" / "scripts" / "export_openapi.py"

OPERATIONS = [
    ("/api/v1/health", "get"),
    ("/api/v1/meta", "get"),
    ("/api/v1/predictions", "post"),
    ("/api/v1/model/metrics", "get"),
    ("/api/v1/predictions/batch", "post"),
    ("/api/v1/predictions/batch/template", "get"),
]


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("export_openapi", SCRIPT)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return _load_script()


@pytest.fixture(scope="module")
def schema(script: ModuleType) -> dict[str, Any]:
    generated: dict[str, Any] = script.generate_openapi()
    return generated


def test_all_six_operations_documented(schema: dict[str, Any]) -> None:
    for path, method in OPERATIONS:
        operation = schema["paths"][path][method]
        assert operation["summary"], path
        assert operation["description"], path
        assert operation["tags"], path


def _example_keys(operation: dict[str, Any], status: str) -> set[str]:
    content = operation["responses"][status]["content"]["application/json"]
    return set(content.get("examples", {}))


def test_prediction_has_request_response_and_error_examples(schema: dict[str, Any]) -> None:
    operation = schema["paths"]["/api/v1/predictions"]["post"]
    request_examples = operation["requestBody"]["content"]["application/json"]["examples"]
    assert set(request_examples) == {"high_risk", "low_risk"}
    ok_schema = schema["components"]["schemas"]["PredictionResponse"]
    assert ok_schema["examples"][0]["top_factors"]
    assert {"VALIDATION_ERROR", "TotalCharges 估算超限"} <= _example_keys(operation, "422")
    assert "MODEL_UNAVAILABLE" in _example_keys(operation, "503")


def test_request_schema_rejects_extra_fields_and_has_examples(schema: dict[str, Any]) -> None:
    features = schema["components"]["schemas"]["CustomerFeatures"]
    assert features["additionalProperties"] is False
    assert len(features["examples"]) == 2
    assert len(features["properties"]) == 19
    assert set(features["required"]) == set(features["properties"]) - {"TotalCharges"}


def test_batch_documents_multipart_and_all_error_codes(schema: dict[str, Any]) -> None:
    operation = schema["paths"]["/api/v1/predictions/batch"]["post"]
    file_schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert file_schema["properties"]["file"]["format"] == "binary"
    assert set(operation["responses"]) >= {"200", "400", "413", "415", "422", "503"}
    assert {"INVALID_ROWS", "MISSING_COLUMNS"} <= _example_keys(operation, "422")
    assert {"FILE_TOO_LARGE", "TOO_MANY_ROWS"} <= _example_keys(operation, "413")
    template = schema["paths"]["/api/v1/predictions/batch/template"]["get"]
    assert "text/csv" in template["responses"]["200"]["content"]


def test_metrics_and_health_error_examples(schema: dict[str, Any]) -> None:
    metrics = schema["paths"]["/api/v1/model/metrics"]["get"]
    assert "METRICS_NOT_FOUND" in _example_keys(metrics, "404")
    health = schema["paths"]["/api/v1/health"]["get"]
    assert "MODEL_UNAVAILABLE" in _example_keys(health, "503")


def test_contract_file_matches_code(script: ModuleType) -> None:
    """與 `export_openapi.py --check` 相同的比對；契約檔過期時此測試失敗。"""
    committed = (REPO_ROOT / "contracts" / "openapi.json").read_text("utf-8").replace("\r\n", "\n")
    assert committed == script.render(script.generate_openapi())
    assert json.loads(committed)["info"]["title"]


def test_check_mode_exit_codes(script: ModuleType, tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"
    assert script.main(["--check", "--output", str(target)]) == 1  # 檔案不存在
    assert script.main(["--output", str(target)]) == 0  # 匯出
    assert script.main(["--check", "--output", str(target)]) == 0
    target.write_text(target.read_text("utf-8") + " ", encoding="utf-8")
    assert script.main(["--check", "--output", str(target)]) == 1  # 過期


def test_docs_page_and_openapi_endpoint_served(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
