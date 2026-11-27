"""單一容器部署：STATIC_DIR 設定時由後端提供前端 SPA。"""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

INDEX_HTML = "<!doctype html><title>spa</title>"


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (root / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    return root


def test_root_and_spa_routes_return_index(
    make_client: Callable[..., TestClient], artifact_dir: Path, static_dir: Path
) -> None:
    client = make_client(model_dir=artifact_dir, static_dir=static_dir)
    for path in ("/", "/batch", "/metrics/deep/link"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == INDEX_HTML
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-content-type-options"] == "nosniff"
    assert client.head("/").status_code == 200


def test_assets_and_root_files_served(
    make_client: Callable[..., TestClient], artifact_dir: Path, static_dir: Path
) -> None:
    client = make_client(model_dir=artifact_dir, static_dir=static_dir)
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/assets/missing.js").status_code == 404


def test_api_docs_and_unknown_api_paths_not_swallowed(
    make_client: Callable[..., TestClient], artifact_dir: Path, static_dir: Path
) -> None:
    client = make_client(model_dir=artifact_dir, static_dir=static_dir)
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"]
    assert "swagger" in client.get("/docs").text.lower()
    missing = client.get("/api/v1/nope")
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/json")


def test_path_traversal_returns_index_not_outside_file(
    make_client: Callable[..., TestClient], artifact_dir: Path, static_dir: Path
) -> None:
    client = make_client(model_dir=artifact_dir, static_dir=static_dir)
    response = client.get("/%2e%2e/secret.txt")
    assert "secret" not in response.text
    nul = client.get("/bad%00name")
    assert nul.status_code == 200
    assert nul.text == INDEX_HTML


def test_without_static_dir_root_is_404(
    make_client: Callable[..., TestClient], artifact_dir: Path
) -> None:
    client = make_client(model_dir=artifact_dir)
    assert client.get("/").status_code == 404


def test_missing_index_refuses_to_start(
    make_client: Callable[..., TestClient], artifact_dir: Path, tmp_path: Path
) -> None:
    with pytest.raises(RuntimeError, match=r"index.html"):
        make_client(model_dir=artifact_dir, static_dir=tmp_path / "empty")
