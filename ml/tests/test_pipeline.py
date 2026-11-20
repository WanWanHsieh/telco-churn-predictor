import json
import logging
import re
from importlib.metadata import version
from pathlib import Path
from typing import Any

import keras
import numpy as np
import pytest

from churn_ml import pipeline
from churn_ml.config import TrainConfig
from churn_ml.data import load_raw_csv, prepare_frame
from churn_ml.export import ARTIFACT_FILES, HASHED_FILES, sha256_file
from churn_ml.pipeline import TrainingResult, run_training
from churn_ml.thresholds import ThresholdChoice, select_threshold


def _read(directory: Path, name: str) -> dict[str, Any]:
    data = json.loads((directory / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _keras_auc(metrics: dict[str, Any]) -> float:
    return float(metrics["models"][1]["metrics"]["roc_auc"])


def test_five_artifacts_with_correct_hashes(trained_run: TrainingResult) -> None:  # AC-4.1
    out = trained_run.config.output_dir
    assert sorted(p.name for p in out.iterdir()) == sorted(ARTIFACT_FILES)

    manifest = _read(out, "manifest.json")
    assert set(manifest["files"]) == set(HASHED_FILES)
    for name, digest in manifest["files"].items():
        assert digest == sha256_file(out / name)
    assert re.fullmatch(r"\d{8}-[0-9a-f]{8}", manifest["model_version"])
    assert manifest["model_version"].split("-")[1] == sha256_file(out / "churn_mlp.keras")[:8]
    assert _read(out, "metrics.json")["model_version"] == manifest["model_version"]


def test_manifest_records_seed_rows_features_and_versions(trained_run: TrainingResult) -> None:
    manifest = _read(trained_run.config.output_dir, "manifest.json")  # AC-4.8
    assert manifest["seed"] == 42
    assert manifest["data"]["rows"] == 120
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["data"]["sha256"])
    assert manifest["data"]["file_name"] == "sample_telco.csv"  # 只記檔名，不洩漏本機路徑
    assert manifest["n_features"] == 45 == len(manifest["feature_names"])
    assert manifest["packages"]["tensorflow"] == version("tensorflow")
    assert manifest["packages"]["keras-nightly"] == version("keras-nightly")
    assert manifest["packages"]["numpy"] == version("numpy")
    assert manifest["packages"]["pandas"] == version("pandas")
    assert manifest["packages"]["scikit-learn"] == version("scikit-learn")
    assert manifest["packages"]["python"].startswith("3.14")
    assert manifest["data"]["cleaning_report"] == {
        "rows": 120,
        "total_charges_blank": 3,
        "total_charges_blank_with_zero_tenure": 3,
    }
    error = manifest["total_charges_estimate_error"]
    assert error["n_rows"] > 0
    assert 0 <= error["median"] <= error["p90"]
    assert manifest["imbalance_strategy"] == "threshold_tuning"
    assert manifest["training"]["config"]["epochs"] == 2


def test_customer_id_is_not_a_feature(trained_run: TrainingResult) -> None:  # AC-4.7
    out = trained_run.config.output_dir
    for names in (
        _read(out, "manifest.json")["feature_names"],
        _read(out, "preprocessor.json")["feature_names"],
    ):
        assert not any("customerid" in n.lower() for n in names)


def test_metrics_content(trained_run: TrainingResult) -> None:
    metrics = _read(trained_run.config.output_dir, "metrics.json")
    assert metrics == trained_run.metrics
    dataset = metrics["dataset"]
    assert dataset["train_size"] + dataset["validation_size"] + dataset["test_size"] == 120
    assert dataset["majority_class_accuracy"] == pytest.approx(
        1 - dataset["test_churn_rate"], abs=1e-4
    )
    assert [m["key"] for m in metrics["models"]] == ["logistic_regression", "keras_mlp"]
    assert metrics["decision_threshold"] == metrics["models"][1]["decision_threshold"]
    experiment = metrics["imbalance_experiment"]
    assert {(r["model"], r["strategy"], r["threshold_rule"]) for r in experiment} == {
        (m, s, r)
        for m in ("logistic_regression", "keras_mlp")
        for s in ("none", "class_weight")
        for r in ("default_0.5", "tuned")
    }
    assert all(r["threshold"] == 0.5 for r in experiment if r["threshold_rule"] == "default_0.5")


def test_explainer_and_model_files_are_usable(trained_run: TrainingResult) -> None:
    out = trained_run.config.output_dir
    explainer = _read(out, "explainer.json")
    assert explainer["method"] == "integrated_gradients"
    assert len(explainer["baseline"]) == 45
    assert 0.0 < explainer["baseline_probability"] < 1.0

    model = keras.saving.load_model(str(out / "churn_mlp.keras"), compile=False)
    probability = np.asarray(model(np.zeros((1, 45), dtype=np.float32), training=False))
    assert probability.shape == (1, 1)


def test_test_set_is_disjoint_and_preprocessor_fit_on_train_only(  # AC-4.4
    trained_run: TrainingResult, sample_csv: Path
) -> None:
    split = trained_run.split
    assert set(split.test).isdisjoint(split.train)
    assert set(split.test).isdisjoint(split.validation)
    assert set(split.train).isdisjoint(split.validation)
    assert len(split.train) + len(split.validation) + len(split.test) == 120

    cleaned, _ = prepare_frame(load_raw_csv(sample_csv))
    stored = _read(trained_run.config.output_dir, "preprocessor.json")["numeric"]["tenure"]["mean"]
    train_mean = float(cleaned["tenure"].iloc[split.train].mean())
    assert stored == pytest.approx(train_mean)
    assert stored != pytest.approx(float(cleaned["tenure"].mean()))  # 不是用全資料或測試集擬合


def test_same_seed_twice_gives_identical_auc(
    trained_run: TrainingResult, tmp_path: Path
) -> None:  # AC-4.6
    again = run_training(
        TrainConfig(data_path=trained_run.config.data_path, output_dir=tmp_path, epochs=2)
    )
    assert _keras_auc(again.metrics) == _keras_auc(trained_run.metrics)
    assert again.metrics["models"] == trained_run.metrics["models"]
    assert (tmp_path / "preprocessor.json").read_text(encoding="utf-8") == (
        trained_run.config.output_dir / "preprocessor.json"
    ).read_text(encoding="utf-8")


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_class_weight_strategy_logs_and_uses_validation_set_only(
    sample_csv: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 記錄每次選門檻時使用的標籤長度：必須是驗證集，不能是測試集（AC-4.4）
    seen: list[int] = []

    def spy(y_true: np.ndarray, proba: np.ndarray, target: float) -> ThresholdChoice:  # type: ignore[type-arg]
        seen.append(len(y_true))
        return select_threshold(y_true, proba, target)

    monkeypatch.setattr(pipeline, "select_threshold", spy)
    handler = _ListHandler()
    logger = logging.getLogger("churn_ml")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        result = run_training(
            TrainConfig(
                data_path=sample_csv,
                output_dir=tmp_path,
                epochs=2,
                imbalance_strategy="class_weight",
            )
        )
    finally:
        logger.removeHandler(handler)

    val_size = len(result.split.validation)
    assert seen == [val_size] * 4  # 兩模型 × 兩種策略，全部只用驗證集
    assert val_size != len(result.split.test)
    assert result.metrics["imbalance_strategy"] == "class_weight"
    assert _read(tmp_path, "manifest.json")["imbalance_strategy"] == "class_weight"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(ARTIFACT_FILES)

    events = {r.event: r.fields for r in handler.records if hasattr(r, "event")}  # type: ignore[attr-defined]
    assert events["data_cleaned"]["total_charges_blank"] == 3  # AC-4.3：log 輸出處理筆數
    assert events["training_start"]["seed"] == 42  # AC-4.8
    assert events["training_start"]["rows"] == 120
    assert events["training_start"]["n_features"] == 45
    assert "tensorflow" in events["training_start"]["packages"]


def test_estimate_error_stats_ignores_blank_and_zero_rows() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {
            "tenure": [10, 10, 0, 5],
            "MonthlyCharges": [50.0, 50.0, 40.0, 20.0],
            "TotalCharges": [500.0, 550.0, float("nan"), 0.0],
        }
    )
    stats = pipeline.estimate_error_stats(frame)
    assert stats["n_rows"] == 2  # 空白列與 0 值列不計
    assert stats["median"] == pytest.approx((0.0 + 50 / 550) / 2, abs=1e-6)
    assert pipeline.estimate_error_stats(frame.iloc[2:])["n_rows"] == 0
