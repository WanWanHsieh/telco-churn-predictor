"""模型產物載入與驗證（design.md 5.1、5.3）。

流程：讀 `manifest.json` → 逐檔比對 SHA-256 → 載入 Keras 模型、`Preprocessor`、`explainer.json`
→ 驗證維度一致。任何一步失敗都只標記「模型不可用」（`ModelState.bundle is None`），
服務照常啟動；health 與預測 API 回 503（AC-1.9、AC-5.3）。

`metrics.json` 不在此載入（缺檔不影響預測；由成效 API 獨立處理，design.md 5.3 第 5 點）。
`KerasModelRunner` 與 Integrated Gradients 的建立與暖機屬於後續任務，這裡只提供已驗證的原料。
"""

import hashlib
import json
import logging
import math
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from churn_api.logging_config import log_event
from churn_api.schemas.common import ModelInfo
from churn_core.preprocessing import Preprocessor

logger = logging.getLogger("churn_api.artifacts")

MODEL_NAME: Final = "keras_mlp"
MODEL_DISPLAY_NAME: Final = "Keras 神經網路"
MANIFEST_FILE: Final = "manifest.json"
MODEL_FILE: Final = "churn_mlp.keras"
PREPROCESSOR_FILE: Final = "preprocessor.json"
EXPLAINER_FILE: Final = "explainer.json"
# 載入模型必須且會被雜湊驗證的檔案（固定檔名，不使用 manifest 內的路徑，避免路徑穿越）
REQUIRED_FILES: Final = (MODEL_FILE, PREPROCESSOR_FILE, EXPLAINER_FILE)
EXPLAINER_METHOD: Final = "integrated_gradients"


class ArtifactLoadError(Exception):
    """模型產物缺檔、雜湊不符或內容不一致。訊息只進 log，不回給使用者。"""


@dataclass(frozen=True)
class ArtifactBundle:
    """已通過雜湊與維度驗證的模型產物。"""

    manifest: Mapping[str, Any]
    keras_model: Any
    preprocessor: Preprocessor
    baseline: NDArray[np.float32]
    baseline_probability: float
    model_version: str
    trained_at: str

    @property
    def model_info(self) -> ModelInfo:
        return ModelInfo(
            name=MODEL_NAME,
            display_name=MODEL_DISPLAY_NAME,
            version=self.model_version,
            trained_at=self.trained_at,
        )


@dataclass(frozen=True)
class ModelState:
    """模型載入結果：`bundle` 為 None 代表不可用，`failure_reason` 說明原因（只進 log）。"""

    bundle: ArtifactBundle | None = None
    failure_reason: str | None = "模型尚未載入"

    @property
    def available(self) -> bool:
        return self.bundle is not None


ArtifactLoader = Callable[[Path], ArtifactBundle]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise ArtifactLoadError(f"缺少檔案：{path.name}") from None
    except OSError as exc:
        raise ArtifactLoadError(f"無法讀取檔案：{path.name}（{type(exc).__name__}）") from exc


def _parse_json_object(data: bytes, name: str) -> dict[str, Any]:
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ArtifactLoadError(f"{name} 不是合法的 JSON") from exc
    if not isinstance(parsed, dict):
        raise ArtifactLoadError(f"{name} 頂層需為物件")
    return parsed


def _expected_hashes(manifest: Mapping[str, Any]) -> dict[str, str]:
    """取出 manifest.files 內三個必要檔案的 SHA-256（值可為字串或含 sha256 欄位的物件）。"""
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ArtifactLoadError("manifest.json 缺少 files 欄位")
    hashes: dict[str, str] = {}
    for name in REQUIRED_FILES:
        entry = files.get(name)
        if isinstance(entry, dict):
            entry = entry.get("sha256")
        if not isinstance(entry, str) or not entry:
            raise ArtifactLoadError(f"manifest.json 未記錄 {name} 的雜湊")
        hashes[name] = entry.strip().lower()
    return hashes


def _load_keras_model(path: Path) -> Any:
    """以 `safe_mode`（預設開啟）載入 Keras 模型；延遲匯入，沒有 TensorFlow 的測試不受影響。"""
    os.environ.setdefault("KERAS_BACKEND", "tensorflow")
    import keras  # 延遲匯入以縮短啟動與測試時間

    return keras.saving.load_model(str(path), compile=False)


def _parse_explainer(data: dict[str, Any], n_features: int) -> tuple[NDArray[np.float32], float]:
    if data.get("method") != EXPLAINER_METHOD:
        raise ArtifactLoadError(f"explainer.json 的 method 需為 {EXPLAINER_METHOD}")
    baseline_raw = data.get("baseline")
    if not isinstance(baseline_raw, list) or len(baseline_raw) != n_features:
        raise ArtifactLoadError(f"explainer.json 的 baseline 長度需為 {n_features}")
    try:
        baseline = np.asarray(baseline_raw, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ArtifactLoadError("explainer.json 的 baseline 含有非數值") from exc
    if not np.isfinite(baseline).all():
        raise ArtifactLoadError("explainer.json 的 baseline 含有非有限數值")
    probability = data.get("baseline_probability")
    if (
        isinstance(probability, bool)
        or not isinstance(probability, int | float)
        or not math.isfinite(probability)
        or not 0 <= probability <= 1
    ):
        raise ArtifactLoadError("explainer.json 的 baseline_probability 需為 0 到 1 的數字")
    return baseline.astype(np.float32), float(probability)


def _check_model_shapes(model: Any, n_features: int) -> None:
    input_shape = getattr(model, "input_shape", None)
    if not (
        isinstance(input_shape, tuple) and len(input_shape) == 2 and input_shape[1] == n_features
    ):
        raise ArtifactLoadError(f"模型輸入維度與特徵數 {n_features} 不一致：{input_shape}")
    output_shape = getattr(model, "output_shape", None)
    if not (isinstance(output_shape, tuple) and len(output_shape) == 2 and output_shape[1] == 1):
        raise ArtifactLoadError(f"模型輸出需為單一機率值：{output_shape}")


def load_artifacts(
    model_dir: Path, *, keras_loader: Callable[[Path], Any] = _load_keras_model
) -> ArtifactBundle:
    """載入並驗證 `model_dir` 內的模型產物；任何問題都拋 `ArtifactLoadError`。

    `keras_loader` 可注入（測試用），預設以 `keras.saving.load_model(compile=False)` 載入。
    """
    manifest = _parse_json_object(_read_bytes(model_dir / MANIFEST_FILE), MANIFEST_FILE)
    expected = _expected_hashes(manifest)

    # 逐檔讀入並比對雜湊（防止只換了一半檔案）；JSON 檔直接用已驗證的位元組解析
    contents: dict[str, bytes] = {}
    for name in REQUIRED_FILES:
        contents[name] = _read_bytes(model_dir / name)
        if sha256_hex(contents[name]) != expected[name]:
            raise ArtifactLoadError(f"雜湊不符：{name}")

    model_version = manifest.get("model_version")
    trained_at = manifest.get("trained_at")
    if not isinstance(model_version, str) or not model_version:
        raise ArtifactLoadError("manifest.json 缺少 model_version")
    if not isinstance(trained_at, str) or not trained_at:
        raise ArtifactLoadError("manifest.json 缺少 trained_at")

    try:
        preprocessor = Preprocessor.from_json(contents[PREPROCESSOR_FILE].decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ArtifactLoadError(f"preprocessor.json 無法載入：{exc}") from exc
    n_features = preprocessor.n_features
    if manifest.get("n_features") != n_features:
        raise ArtifactLoadError(f"manifest 的 n_features 與前處理器的 {n_features} 維不一致")
    if "feature_names" in manifest and manifest["feature_names"] != preprocessor.feature_names:
        raise ArtifactLoadError("manifest 的 feature_names 與 preprocessor.json 不一致")

    baseline, baseline_probability = _parse_explainer(
        _parse_json_object(contents[EXPLAINER_FILE], EXPLAINER_FILE), n_features
    )

    keras_model = keras_loader(model_dir / MODEL_FILE)
    _check_model_shapes(keras_model, n_features)

    return ArtifactBundle(
        manifest=manifest,
        keras_model=keras_model,
        preprocessor=preprocessor,
        baseline=baseline,
        baseline_probability=baseline_probability,
        model_version=model_version,
        trained_at=trained_at,
    )


def load_model_state(model_dir: Path, loader: ArtifactLoader = load_artifacts) -> ModelState:
    """載入模型；失敗時 log `model_load_failed` 並回傳不可用狀態，不拋例外（服務照常啟動）。"""
    started = time.perf_counter()
    try:
        bundle = loader(model_dir)
    except ArtifactLoadError as exc:
        log_event(logger, logging.ERROR, "model_load_failed", "模型載入失敗", reason=str(exc))
        return ModelState(bundle=None, failure_reason=str(exc))
    except Exception as exc:  # 載入第三方格式可能拋任何例外；一律標記不可用
        reason = f"{type(exc).__name__}: {str(exc)[:300]}"
        log_event(
            logger, logging.ERROR, "model_load_failed", "模型載入失敗", exc_info=exc, reason=reason
        )
        return ModelState(bundle=None, failure_reason=reason)

    log_event(
        logger,
        logging.INFO,
        "model_loaded",
        "模型載入完成",
        version=bundle.model_version,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return ModelState(bundle=bundle, failure_reason=None)
