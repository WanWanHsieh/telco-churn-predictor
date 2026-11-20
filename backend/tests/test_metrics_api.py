"""GET /api/v1/model/metrics：缺檔 404、格式錯 500、內容與檔案相同、不依賴預測模型。"""

import json
import shutil
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

URL = "/api/v1/model/metrics"


def test_missing_metrics_returns_404(
    make_client: Callable[..., TestClient], artifact_dir: Path
) -> None:
    response = make_client(model_dir=artifact_dir).get(URL)
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "METRICS_NOT_FOUND"
    assert set(error) == {"code", "message", "details", "meta", "request_id"}


def test_metrics_match_file_exactly(
    make_client: Callable[..., TestClient], artifact_dir: Path, real_models_dir: Path
) -> None:
    """AC-3.6：回應內容與 metrics.json 逐欄相同（含 ROC 兩條 101 點曲線）。"""
    shutil.copy(real_models_dir / "metrics.json", artifact_dir / "metrics.json")
    response = make_client(model_dir=artifact_dir).get(URL)
    assert response.status_code == 200
    expected = json.loads((artifact_dir / "metrics.json").read_text("utf-8"))
    assert response.json() == expected
    body = response.json()
    assert [m["key"] for m in body["models"]] == ["logistic_regression", "keras_mlp"]
    assert all(len(m["roc_curve"]["fpr"]) == 101 for m in body["models"])
    assert body["decision_threshold"] == body["models"][1]["decision_threshold"]


def test_metrics_do_not_depend_on_prediction_model(
    make_client: Callable[..., TestClient], tmp_path: Path, real_models_dir: Path
) -> None:
    model_dir = tmp_path / "only_metrics"
    model_dir.mkdir()
    shutil.copy(real_models_dir / "metrics.json", model_dir / "metrics.json")
    client = make_client(model_dir=model_dir)
    assert client.get("/api/v1/health").status_code == 503  # 模型不可用
    assert client.get(URL).status_code == 200  # 成效資料仍可取得


def test_metrics_response_is_fast(
    make_client: Callable[..., TestClient], tmp_path: Path, real_models_dir: Path
) -> None:
    """NFR-3：啟動時載入記憶體，回應 < 300ms（單元層級的粗略驗證；Docker 實測由 T14 負責）。"""
    shutil.copy(real_models_dir / "metrics.json", tmp_path / "metrics.json")
    client = make_client(model_dir=tmp_path)
    client.get(URL)
    started = time.perf_counter()
    for _ in range(20):
        assert client.get(URL).status_code == 200
    assert (time.perf_counter() - started) / 20 < 0.3


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '{"primary_model": "keras_mlp"}',  # 結構不完整
        b"\xff\xfe\x00bad",  # 非 UTF-8
    ],
)
def test_malformed_metrics_returns_500_without_leaking(
    make_client: Callable[..., TestClient], tmp_path: Path, content: str | bytes
) -> None:
    path = tmp_path / "metrics.json"
    path.write_bytes(content if isinstance(content, bytes) else content.encode())
    response = make_client(model_dir=tmp_path).get(URL)
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "metrics.json" not in response.text
    assert "Traceback" not in response.text


def test_extra_field_in_metrics_file_is_treated_as_malformed(
    make_client: Callable[..., TestClient], tmp_path: Path, real_models_dir: Path
) -> None:
    data = json.loads((real_models_dir / "metrics.json").read_text("utf-8"))
    data["surprise"] = 1
    (tmp_path / "metrics.json").write_text(json.dumps(data), encoding="utf-8")
    assert make_client(model_dir=tmp_path).get(URL).status_code == 500
