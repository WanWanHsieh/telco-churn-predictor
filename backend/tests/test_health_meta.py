"""health／meta API、CORS、服務在模型缺失時照常啟動（AC-5.3、AC-1.9、NFR-8）。"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from churn_api.main import create_app
from churn_api.settings import Settings

ERROR_KEYS = {"code", "message", "details", "meta", "request_id"}
ALLOWED_ORIGIN = "http://localhost:8080"


def test_health_ok_with_model_version(
    make_client: Callable[..., TestClient], artifact_dir: Path
) -> None:
    client = make_client(model_dir=artifact_dir)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    manifest = json.loads((artifact_dir / "manifest.json").read_text("utf-8"))
    assert body["model"] == {
        "name": "keras_mlp",
        "display_name": "Keras 神經網路",
        "version": manifest["model_version"],
        "trained_at": "2026-11-20T08:00:00Z",
    }
    assert response.headers["x-request-id"]


@pytest.mark.parametrize("missing", ["manifest.json", "churn_mlp.keras", "preprocessor.json"])
def test_health_503_when_file_missing_but_service_keeps_running(
    make_client: Callable[..., TestClient], artifact_dir: Path, missing: str
) -> None:
    (artifact_dir / missing).unlink()
    client = make_client(model_dir=artifact_dir)  # 啟動不拋例外

    response = client.get("/api/v1/health")
    assert response.status_code == 503
    error = response.json()["error"]
    assert set(error) == ERROR_KEYS
    assert error["code"] == "MODEL_UNAVAILABLE"
    assert error["message"] == "模型尚未載入，服務暫時無法使用。"
    assert error["request_id"] == response.headers["x-request-id"]
    assert str(artifact_dir) not in response.text  # 不洩漏路徑
    assert missing not in response.text

    # 服務仍在運作：meta 不依賴模型，未知路徑回統一的 404
    assert client.get("/api/v1/meta").status_code == 200
    assert client.get("/nope").status_code == 404


def test_health_503_when_hash_mismatch(
    make_client: Callable[..., TestClient], artifact_dir: Path
) -> None:
    with (artifact_dir / "explainer.json").open("ab") as handle:
        handle.write(b"\n")
    client = make_client(model_dir=artifact_dir)
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_UNAVAILABLE"


def test_health_503_when_model_dir_does_not_exist(
    make_client: Callable[..., TestClient], tmp_path: Path
) -> None:
    client = make_client(model_dir=tmp_path / "does-not-exist")
    assert client.get("/api/v1/health").status_code == 503


def test_health_503_when_lifespan_not_run(make_settings: Callable[..., Settings]) -> None:
    """未執行 lifespan（沒有 model_state）時視為不可用，回 503 而不是 500。"""
    client = TestClient(create_app(make_settings()), raise_server_exceptions=False)
    assert client.get("/api/v1/health").status_code == 503


def test_dependency_override_replaces_model_state(
    make_client: Callable[..., TestClient],
    make_settings: Callable[..., Settings],
    artifact_dir: Path,
) -> None:
    from churn_api.dependencies import get_model_state
    from churn_api.inference.artifacts import ModelState, load_artifacts

    bundle = load_artifacts(artifact_dir)
    app = create_app(make_settings(model_dir=artifact_dir / "missing"))
    app.dependency_overrides[get_model_state] = lambda: ModelState(
        bundle=bundle, failure_reason=None
    )
    client = make_client(app)
    assert client.get("/api/v1/health").status_code == 200


def test_meta_matches_design(make_client: Callable[..., TestClient], tmp_path: Path) -> None:
    client = make_client(model_dir=tmp_path / "no-model")  # 模型不可用也能回
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    assert response.text.count('"min":0,') == 3 and '"max":72' in response.text  # 整數不輸出成 0.0
    assert response.json() == {
        "risk_thresholds": {"medium": 0.30, "high": 0.60},
        "batch_limits": {"max_file_bytes": 5242880, "max_rows": 10000},
        "input_ranges": {
            "tenure": {"min": 0, "max": 72},
            "MonthlyCharges": {"min": 0, "max": 200},
            "TotalCharges": {"min": 0, "max": 10000},
        },
    }


def test_meta_reflects_settings(make_client: Callable[..., TestClient]) -> None:
    client = make_client(
        risk_medium_threshold=0.25,
        risk_high_threshold=0.7,
        batch_max_file_bytes=1024,
        batch_max_rows=50,
    )
    body = client.get("/api/v1/meta").json()
    assert body["risk_thresholds"] == {"medium": 0.25, "high": 0.7}
    assert body["batch_limits"] == {"max_file_bytes": 1024, "max_rows": 50}


def test_cors_allows_only_configured_origins(make_client: Callable[..., TestClient]) -> None:
    client = make_client(cors_allow_origins="http://localhost:8080")

    allowed = client.get("/api/v1/meta", headers={"Origin": ALLOWED_ORIGIN})
    assert allowed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "access-control-allow-credentials" not in allowed.headers
    assert "x-request-id" in allowed.headers["access-control-expose-headers"].lower()

    denied = client.get("/api/v1/meta", headers={"Origin": "http://evil.example.com"})
    assert denied.status_code == 200  # CORS 由瀏覽器強制；伺服器只是不給放行標頭
    assert "access-control-allow-origin" not in denied.headers

    preflight_ok = client.options(
        "/api/v1/predictions",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight_ok.status_code == 200
    assert preflight_ok.headers["access-control-allow-origin"] == ALLOWED_ORIGIN

    preflight_bad = client.options(
        "/api/v1/predictions",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight_bad.status_code == 400
    assert "access-control-allow-origin" not in preflight_bad.headers
    assert preflight_bad.headers["x-request-id"]  # 預檢回應也帶 request id


def test_gzip_compresses_large_responses(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    openapi = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert openapi.status_code == 200
    assert openapi.headers.get("content-encoding") == "gzip"


def test_openapi_documents_health_and_meta(make_client: Callable[..., TestClient]) -> None:
    schema: dict[str, Any] = make_client().get("/openapi.json").json()
    health = schema["paths"]["/api/v1/health"]["get"]
    assert health["summary"]
    assert "503" in health["responses"]
    assert "examples" in health["responses"]["503"]["content"]["application/json"]
    meta = schema["paths"]["/api/v1/meta"]["get"]
    assert meta["description"]
    assert schema["info"]["title"]
    docs = make_client().get("/docs")
    assert docs.status_code == 200
