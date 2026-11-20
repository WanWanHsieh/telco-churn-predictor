"""模型產物載入：雜湊驗證、缺檔／竄改 → unavailable 而不中止（design.md 5.3、AC-1.9）。"""

import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from churn_api.inference.artifacts import (
    ArtifactBundle,
    ArtifactLoadError,
    ModelState,
    load_artifacts,
    load_model_state,
    sha256_hex,
)
from churn_api.logging_config import configure_logging
from churn_core.preprocessing import N_FEATURES


def _fake_keras_loader(path: Path) -> Any:
    class FakeModel:
        input_shape = (None, N_FEATURES)
        output_shape = (None, 1)

    return FakeModel()


def _read(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return data


def test_load_real_keras_model(artifact_dir: Path) -> None:
    bundle = load_artifacts(artifact_dir)
    assert bundle.keras_model.input_shape == (None, N_FEATURES)
    assert bundle.preprocessor.n_features == N_FEATURES
    assert bundle.baseline.shape == (N_FEATURES,)
    assert bundle.baseline.dtype == np.float32
    assert bundle.baseline_probability == 0.5
    assert bundle.model_version.startswith("20261120-")
    info = bundle.model_info
    assert (info.name, info.display_name) == ("keras_mlp", "Keras 神經網路")
    assert info.trained_at == "2026-11-20T08:00:00Z"


@pytest.mark.parametrize(
    "name", ["manifest.json", "churn_mlp.keras", "preprocessor.json", "explainer.json"]
)
def test_missing_file_is_load_error(artifact_dir: Path, name: str) -> None:
    (artifact_dir / name).unlink()
    with pytest.raises(ArtifactLoadError, match=name):
        load_artifacts(artifact_dir, keras_loader=_fake_keras_loader)


def test_missing_directory_is_load_error(tmp_path: Path) -> None:
    with pytest.raises(ArtifactLoadError, match=r"manifest\.json"):
        load_artifacts(tmp_path / "nope", keras_loader=_fake_keras_loader)


@pytest.mark.parametrize("name", ["churn_mlp.keras", "preprocessor.json", "explainer.json"])
def test_tampered_file_hash_mismatch(artifact_dir: Path, name: str) -> None:
    with (artifact_dir / name).open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ArtifactLoadError, match=f"雜湊不符：{name}"):
        load_artifacts(artifact_dir, keras_loader=_fake_keras_loader)


def test_swapped_half_of_files_is_detected(artifact_dir: Path, tmp_path: Path) -> None:
    """只換掉其中一個檔案（manifest 沒跟著換）→ 雜湊不符。"""
    explainer = _read(artifact_dir / "explainer.json")
    explainer["baseline_probability"] = 0.9
    (artifact_dir / "explainer.json").write_text(json.dumps(explainer), encoding="utf-8")
    with pytest.raises(ArtifactLoadError, match="雜湊不符"):
        load_artifacts(artifact_dir, keras_loader=_fake_keras_loader)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.pop("files"),
        lambda m: m["files"].pop("explainer.json"),
        lambda m: m.pop("model_version"),
        lambda m: m.pop("trained_at"),
        lambda m: m.update(n_features=44),
        lambda m: m.update(feature_names=["x"]),
    ],
)
def test_invalid_manifest(artifact_dir: Path, mutate: Any) -> None:
    manifest = _read(artifact_dir / "manifest.json")
    mutate(manifest)
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactLoadError):
        load_artifacts(artifact_dir, keras_loader=_fake_keras_loader)


def test_manifest_not_json_object(artifact_dir: Path) -> None:
    (artifact_dir / "manifest.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ArtifactLoadError, match="頂層需為物件"):
        load_artifacts(artifact_dir, keras_loader=_fake_keras_loader)
    (artifact_dir / "manifest.json").write_text("not json", encoding="utf-8")
    with pytest.raises(ArtifactLoadError, match="不是合法的 JSON"):
        load_artifacts(artifact_dir, keras_loader=_fake_keras_loader)


def test_manifest_hash_entry_may_be_object(artifact_dir: Path) -> None:
    manifest = _read(artifact_dir / "manifest.json")
    manifest["files"] = {k: {"sha256": v.upper()} for k, v in manifest["files"].items()}
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert load_artifacts(artifact_dir, keras_loader=_fake_keras_loader).model_version


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.update(method="shap"),
        lambda e: e.update(baseline=[0.0] * 44),
        lambda e: e.update(baseline=["a"] * N_FEATURES),
        lambda e: e.update(baseline=[float("inf")] + [0.0] * (N_FEATURES - 1)),
        lambda e: e.update(baseline_probability=1.5),
        lambda e: e.update(baseline_probability=True),
        lambda e: e.pop("baseline_probability"),
    ],
)
def test_invalid_explainer(
    artifact_dir: Path, mutate: Any, rewrite_manifest: Callable[[Path], Any]
) -> None:
    explainer = _read(artifact_dir / "explainer.json")
    mutate(explainer)
    (artifact_dir / "explainer.json").write_text(json.dumps(explainer), encoding="utf-8")
    rewrite_manifest(artifact_dir)  # 雜湊對齊，單獨測內容檢查
    with pytest.raises(ArtifactLoadError, match=r"explainer\.json"):
        load_artifacts(artifact_dir, keras_loader=_fake_keras_loader)


def test_invalid_preprocessor_content(artifact_dir: Path) -> None:
    (artifact_dir / "preprocessor.json").write_text('{"format_version": 99}', encoding="utf-8")
    manifest = _read(artifact_dir / "manifest.json")
    manifest["files"]["preprocessor.json"] = sha256_hex(
        (artifact_dir / "preprocessor.json").read_bytes()
    )
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactLoadError, match=r"preprocessor\.json"):
        load_artifacts(artifact_dir, keras_loader=_fake_keras_loader)


@pytest.mark.parametrize(
    ("input_shape", "output_shape"),
    [((None, 44), (None, 1)), ((None, N_FEATURES), (None, 2)), ([(None, N_FEATURES)], (None, 1))],
)
def test_model_shape_mismatch(artifact_dir: Path, input_shape: Any, output_shape: Any) -> None:
    class BadModel:
        pass

    bad = BadModel()
    bad.input_shape = input_shape  # type: ignore[attr-defined]
    bad.output_shape = output_shape  # type: ignore[attr-defined]
    with pytest.raises(ArtifactLoadError, match="模型"):
        load_artifacts(artifact_dir, keras_loader=lambda _: bad)


def test_corrupt_keras_file_marks_unavailable_without_raising(
    artifact_dir: Path, rewrite_manifest: Callable[[Path], Any]
) -> None:
    """Keras 檔內容損壞（但雜湊已對齊）→ 載入拋第三方例外，仍只標記不可用。"""
    (artifact_dir / "churn_mlp.keras").write_bytes(b"not a keras archive")
    rewrite_manifest(artifact_dir)
    state = load_model_state(artifact_dir)
    assert not state.available
    assert state.bundle is None
    assert state.failure_reason


def test_load_model_state_success_logs_model_loaded(artifact_dir: Path) -> None:
    stream = io.StringIO()
    configure_logging("INFO", "production", stream=stream)
    try:
        state = load_model_state(artifact_dir, load_artifacts)
    finally:
        configure_logging("INFO", "production")
    assert state.available
    assert state.failure_reason is None
    assert isinstance(state.bundle, ArtifactBundle)
    event = json.loads(stream.getvalue().splitlines()[-1])
    assert event["event"] == "model_loaded"
    assert event["version"] == state.bundle.model_version
    assert event["duration_ms"] >= 0


def test_load_model_state_failure_logs_and_does_not_raise(tmp_path: Path) -> None:
    stream = io.StringIO()
    configure_logging("INFO", "production", stream=stream)
    try:
        state = load_model_state(tmp_path / "missing")
    finally:
        configure_logging("INFO", "production")
    assert state == ModelState(bundle=None, failure_reason="缺少檔案：manifest.json")
    event = json.loads(stream.getvalue().splitlines()[-1])
    assert event["event"] == "model_load_failed"
    assert event["level"] == "ERROR"
    assert event["reason"] == "缺少檔案：manifest.json"


def test_unexpected_loader_exception_is_contained() -> None:
    def explode(_: Path) -> ArtifactBundle:
        raise MemoryError("simulated")

    # MemoryError 也屬 Exception 子類：標記不可用，不讓服務掛掉
    state = load_model_state(Path("."), explode)
    assert not state.available
    assert "MemoryError" in (state.failure_reason or "")


def test_default_model_state_is_unavailable() -> None:
    assert not ModelState().available
