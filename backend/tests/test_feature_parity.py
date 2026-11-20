"""特徵一致性（NFR-6）與真實產物整合：訓練路徑與 API／批次路徑的特徵向量逐位元相同。

訓練路徑：`clean_raw_frame`（含 TotalCharges 空白字串）→ `impute_total_charges` → `transform`。
API 路徑：請求本體 → `CustomerFeatures` → `PredictionService`（以記錄用 runner 取得向量）。
批次路徑：CSV 位元組 → `parse_batch_csv` → `BatchService`。
另以進版控的 `models/` 正式產物（T3 訓練管線的輸出）載入並預測，確認訓練與推論銜接。
"""

import csv
import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from churn_api.inference.artifacts import load_artifacts
from churn_api.inference.explainer import IntegratedGradientsExplainer
from churn_api.inference.model_runner import KerasModelRunner
from churn_api.schemas.common import ModelInfo, RiskThresholds
from churn_api.schemas.prediction import CustomerFeatures
from churn_api.services.batch_service import BatchService
from churn_api.services.csv_parser import parse_batch_csv
from churn_api.services.prediction_service import PredictionService
from churn_core.cleaning import clean_raw_frame
from churn_core.examples import HIGH_RISK_EXAMPLE, LOW_RISK_EXAMPLE
from churn_core.imputation import impute_total_charges
from churn_core.preprocessing import N_FEATURES, Preprocessor
from churn_core.schema import (
    FEATURES,
    INTERNET_ADDON_FEATURES,
    LEGAL_VALUES,
    NO_INTERNET_SERVICE,
    NO_PHONE_SERVICE,
)

INFO = ModelInfo(name="keras_mlp", display_name="Keras", version="v", trained_at="2026-11-20")
THRESHOLDS = RiskThresholds(medium=0.3, high=0.6)


def _raw_rows(count: int = 60, seed: int = 11) -> list[dict[str, str]]:
    """產生像原始 CSV 的列（全是字串；含 TotalCharges 空白、tenure=0、第 3 位小數為 5 的邊界）。"""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, str]] = []
    for i in range(count):
        row: dict[str, str] = {}
        for name, values in LEGAL_VALUES.items():
            row[name] = str(rng.choice(list(values)))
        row["SeniorCitizen"] = str(int(rng.integers(0, 2)))
        if row["PhoneService"] == "No":
            row["MultipleLines"] = NO_PHONE_SERVICE
        elif row["MultipleLines"] == NO_PHONE_SERVICE:
            row["MultipleLines"] = "No"
        for name in INTERNET_ADDON_FEATURES:
            if row["InternetService"] == "No":
                row[name] = NO_INTERNET_SERVICE
            elif row[name] == NO_INTERNET_SERVICE:
                row[name] = "Yes"
        tenure = 0 if i % 9 == 0 else int(rng.integers(1, 73))
        monthly = round(float(rng.uniform(18.25, 118.75)), 2)
        row["tenure"] = str(tenure)
        row["MonthlyCharges"] = str(monthly)
        if tenure == 0 or i % 4 == 0:
            row["TotalCharges"] = " "  # 原始資料的空白字串
        else:
            row["TotalCharges"] = str(round(monthly * tenure * float(rng.uniform(0.9, 1.1)), 2))
        rows.append(row)
    edge = dict(rows[1])  # 估算值第 3 位小數剛好是 5：1 × 20.005 → half-up 20.01
    edge.update(tenure="1", MonthlyCharges="20.005", TotalCharges=" ")
    rows.append(edge)
    return rows


def _api_record(raw: dict[str, str]) -> dict[str, Any]:
    """原始列 → API 請求本體（型別化；空白 TotalCharges → 省略）。"""
    record: dict[str, Any] = dict(raw)
    record["SeniorCitizen"] = int(raw["SeniorCitizen"])
    record["tenure"] = int(raw["tenure"])
    record["MonthlyCharges"] = float(raw["MonthlyCharges"])
    if raw["TotalCharges"].strip():
        record["TotalCharges"] = float(raw["TotalCharges"])
    else:
        record.pop("TotalCharges")
    return record


def _training_matrix(
    rows: list[dict[str, str]], preprocessor: Preprocessor
) -> np.ndarray[Any, Any]:
    cleaned, _ = clean_raw_frame(pd.DataFrame(rows))
    return preprocessor.transform(impute_total_charges(cleaned).frame)


@pytest.fixture(scope="module")
def preprocessor() -> Preprocessor:
    models = Path(__file__).resolve().parents[2] / "models"
    return Preprocessor.from_json((models / "preprocessor.json").read_text("utf-8"))


def test_api_path_vectors_are_bitwise_equal_to_training_path(
    preprocessor: Preprocessor, fake_runner: Callable[..., Any], fake_explainer: Callable[..., Any]
) -> None:
    rows = _raw_rows()
    expected = _training_matrix(rows, preprocessor)

    runner = fake_runner()
    service = PredictionService(
        runner, fake_explainer(np.zeros(N_FEATURES)), preprocessor, INFO, THRESHOLDS
    )
    for raw in rows:
        service.predict(CustomerFeatures.model_validate(_api_record(raw)))

    actual = np.vstack([call for call in runner.calls])
    assert actual.shape == expected.shape == (len(rows), N_FEATURES)
    assert actual.dtype == expected.dtype == np.float32
    assert actual.tobytes() == expected.tobytes()  # 逐位元相同


def test_batch_path_vectors_are_bitwise_equal_to_training_path(
    preprocessor: Preprocessor, fake_runner: Callable[..., Any]
) -> None:
    rows = _raw_rows()
    expected = _training_matrix(rows, preprocessor)

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(FEATURES))
    writer.writeheader()
    writer.writerows(rows)  # TotalCharges 為單一空白的列，等同原始資料檔
    parsed = parse_batch_csv(
        "x.csv", buffer.getvalue().encode(), max_file_bytes=10_000_000, max_rows=1000
    )
    runner = fake_runner()
    BatchService(runner, preprocessor, INFO, THRESHOLDS).predict(parsed)

    assert np.vstack(runner.calls).tobytes() == expected.tobytes()


def test_single_and_batch_probabilities_agree(
    preprocessor: Preprocessor, fake_runner: Callable[..., Any], fake_explainer: Callable[..., Any]
) -> None:
    """R6：同一顧客單筆與批次的機率（3 位小數）一致。"""
    rows = _raw_rows(20)
    single = PredictionService(
        fake_runner(), fake_explainer(np.zeros(N_FEATURES)), preprocessor, INFO, THRESHOLDS
    )
    singles = [
        single.predict(CustomerFeatures.model_validate(_api_record(r))).probability for r in rows
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(FEATURES))
    writer.writeheader()
    writer.writerows(rows)
    parsed = parse_batch_csv("x.csv", buffer.getvalue().encode(), max_file_bytes=10**7, max_rows=99)
    batch = BatchService(fake_runner(), preprocessor, INFO, THRESHOLDS).predict(parsed)
    assert [r.probability for r in batch.results] == singles


# ----------------------------------------------------------- 正式產物（models/）整合
def test_real_artifacts_load_and_explainer_is_consistent(real_models_dir: Path) -> None:
    """T3 訓練管線的實際輸出 → `load_artifacts` → runner／IG：explainer.json 與模型自洽。"""
    bundle = load_artifacts(real_models_dir)
    runner = KerasModelRunner(bundle.keras_model)
    explainer = IntegratedGradientsExplainer(
        bundle.keras_model, bundle.baseline, bundle.baseline_probability, steps=64
    )
    frame = pd.DataFrame([dict(HIGH_RISK_EXAMPLE)], columns=list(FEATURES))
    vector = bundle.preprocessor.transform(impute_total_charges(frame).frame)

    attribution, p_base, p_x = explainer.attribute_with_endpoints(vector[0])
    assert p_x == pytest.approx(runner.predict_proba(vector)[0], abs=1e-6)
    assert p_base == pytest.approx(bundle.baseline_probability, abs=1e-4)  # 基準機率與檔案一致
    assert abs(attribution.sum() - (p_x - p_base)) < 0.01  # 完整性
    assert bundle.preprocessor.n_features == N_FEATURES


def test_real_artifacts_end_to_end_through_api(
    make_client: Callable[..., TestClient], real_models_dir: Path
) -> None:
    client = make_client(model_dir=real_models_dir)
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["model"]["version"] == load_artifacts(real_models_dir).model_version

    high = client.post("/api/v1/predictions", json=dict(HIGH_RISK_EXAMPLE)).json()
    low = client.post("/api/v1/predictions", json=dict(LOW_RISK_EXAMPLE)).json()
    assert high["probability"] > low["probability"]
    assert len(high["top_factors"]) == len(low["top_factors"]) == 5
    assert [f["feature"] for f in high["top_factors"]] != [f["feature"] for f in low["top_factors"]]
    assert high["total_charges"]["is_estimated"] is True
    # 訓練與推論共用同一份前處理器：API 的結果與直接用 bundle 算出的機率一致
    bundle = load_artifacts(real_models_dir)
    frame = pd.DataFrame(
        [{**dict(HIGH_RISK_EXAMPLE), "TotalCharges": 100.0}], columns=list(FEATURES)
    )
    vector = bundle.preprocessor.transform(frame)
    direct = float(bundle.keras_model(vector, training=False).numpy().reshape(-1)[0])
    assert high["probability"] == pytest.approx(direct, abs=5e-4)
