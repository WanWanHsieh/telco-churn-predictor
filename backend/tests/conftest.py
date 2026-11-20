"""backend 測試共用 fixture。

測試用的模型產物目錄由 fixture 在臨時目錄產生（小型 Keras 模型＋由範例擬合的前處理器），
不依賴 `models/`（T4 才會產出）。
"""

import hashlib
import json
import os
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from churn_api.main import create_app
from churn_api.settings import Settings
from churn_core.examples import EXAMPLES
from churn_core.preprocessing import N_FEATURES, Preprocessor

os.environ.setdefault("KERAS_BACKEND", "tensorflow")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(model_dir: Path) -> dict[str, Any]:
    """依目錄內現有的三個產物檔重寫 manifest.json（測試竄改檔案後可重新對齊雜湊）。"""
    preprocessor = Preprocessor.from_json((model_dir / "preprocessor.json").read_text("utf-8"))
    files = {
        name: sha256_file(model_dir / name)
        for name in ("churn_mlp.keras", "preprocessor.json", "explainer.json")
    }
    manifest: dict[str, Any] = {
        "model_version": f"20261120-{files['churn_mlp.keras'][:8]}",
        "trained_at": "2026-11-20T08:00:00Z",
        "seed": 42,
        "n_features": N_FEATURES,
        "feature_names": preprocessor.feature_names,
        "files": files,
    }
    (model_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


@pytest.fixture(scope="session")
def _artifact_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """session 層級只建一次的模型產物（小型 Keras 模型，固定種子）。"""
    import keras

    model_dir = tmp_path_factory.mktemp("artifact_template")
    keras.utils.set_random_seed(0)
    model = keras.Sequential(
        [keras.Input(shape=(N_FEATURES,)), keras.layers.Dense(1, activation="sigmoid")]
    )
    model.save(model_dir / "churn_mlp.keras")

    rows = []
    for example in EXAMPLES.values():
        row = dict(example)
        if row.get("TotalCharges") is None:
            row["TotalCharges"] = 100.0
        rows.append(row)
    preprocessor = Preprocessor().fit(pd.DataFrame(rows))
    (model_dir / "preprocessor.json").write_text(preprocessor.to_json(), encoding="utf-8")

    explainer = {
        "method": "integrated_gradients",
        "baseline": np.zeros(N_FEATURES).tolist(),
        "baseline_probability": 0.5,
    }
    (model_dir / "explainer.json").write_text(json.dumps(explainer), encoding="utf-8")
    write_manifest(model_dir)
    return model_dir


@pytest.fixture
def artifact_dir(_artifact_template: Path, tmp_path: Path) -> Path:
    """每個測試獨立的模型目錄副本，可安全地刪檔或竄改。"""
    target = tmp_path / "models"
    shutil.copytree(_artifact_template, target)
    return target


@pytest.fixture
def rewrite_manifest() -> Callable[[Path], dict[str, Any]]:
    """回傳 `write_manifest`：竄改產物內容後，用來重新對齊 manifest 雜湊。"""
    return write_manifest


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    """建立不讀 .env 的 Settings；以關鍵字覆寫欄位。"""

    def factory(**overrides: Any) -> Settings:
        return Settings(_env_file=None, **overrides)

    return factory


@pytest.fixture
def make_client(
    make_settings: Callable[..., Settings],
) -> Iterator[Callable[..., TestClient]]:
    """建立 TestClient 的工廠（會執行 lifespan，結束時自動關閉）。"""
    opened: list[TestClient] = []

    def factory(app: FastAPI | None = None, **settings_overrides: Any) -> TestClient:
        application = app or create_app(make_settings(**settings_overrides))
        client = TestClient(application, raise_server_exceptions=False)
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


# --------------------------------------------------------------- T6／T7 共用
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_MODELS_DIR = REPO_ROOT / "models"


class FakeRunner:
    """測試用 ModelRunner：記錄收到的前處理矩陣；機率為向量的確定性函數（不同輸入得不同機率）。"""

    def __init__(self, fixed: float | None = None) -> None:
        self.fixed = fixed
        self.calls: list[np.ndarray[Any, Any]] = []

    def predict_proba(self, features: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        self.calls.append(np.array(features, copy=True))
        if self.fixed is not None:
            return np.full(len(features), self.fixed, dtype=np.float64)
        logits = features.astype(np.float64).sum(axis=1) * 0.1
        return np.asarray(1.0 / (1.0 + np.exp(-logits)), dtype=np.float64)


class FakeExplainer:
    """測試用 Explainer：回傳指定的 45 維歸因。"""

    def __init__(self, attribution: np.ndarray[Any, Any], baseline_probability: float = 0.25):
        self._attribution = np.asarray(attribution, dtype=np.float64)
        self._baseline = baseline_probability

    @property
    def baseline_probability(self) -> float:
        return self._baseline

    def attribute(self, features: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        return self._attribution


@pytest.fixture
def fake_runner() -> Callable[..., FakeRunner]:
    return FakeRunner


@pytest.fixture
def fake_explainer() -> Callable[..., FakeExplainer]:
    return FakeExplainer


@pytest.fixture
def record() -> Callable[..., dict[str, Any]]:
    """合法的單筆請求本體（高風險範例，省略 TotalCharges）；kwargs 覆寫、DROP=[欄名] 移除。"""

    def factory(**overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = dict(EXAMPLES["high_risk"])
        drop = overrides.pop("DROP", [])
        data.update(overrides)
        for name in drop:
            data.pop(name, None)
        return data

    return factory


@pytest.fixture
def make_csv() -> Callable[..., bytes]:
    """把紀錄清單轉成 CSV 位元組。None／缺少的鍵輸出為空白儲存格。"""
    import csv
    import io

    from churn_core.schema import FEATURES

    def factory(
        rows: list[dict[str, Any]],
        columns: list[str] | None = None,
        *,
        bom: bool = False,
        eol: str = "\r\n",
    ) -> bytes:
        cols = columns if columns is not None else ["customerID", *FEATURES]
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator=eol)
        writer.writerow(cols)
        for row in rows:
            writer.writerow(["" if row.get(c) is None else row[c] for c in cols])
        data = buffer.getvalue().encode("utf-8")
        return (b"\xef\xbb\xbf" + data) if bom else data

    return factory


@pytest.fixture(scope="session")
def real_models_dir() -> Path:
    """進版控的正式模型產物（T4）；測試只讀不寫。"""
    assert (REAL_MODELS_DIR / "manifest.json").is_file(), "缺少 models/ 正式產物"
    return REAL_MODELS_DIR
