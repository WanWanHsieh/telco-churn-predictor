from pathlib import Path

import numpy as np
import pytest

from churn_ml.config import KAGGLE_URL, TrainConfig
from churn_ml.data import (
    DataFileNotFoundError,
    DataValidationError,
    Split,
    load_raw_csv,
    prepare_frame,
    split_indices,
)


def test_missing_file_raises_friendly_error(tmp_path: Path) -> None:  # AC-4.2
    with pytest.raises(DataFileNotFoundError) as info:
        load_raw_csv(tmp_path / "nope.csv")
    message = str(info.value)
    assert "找不到資料檔，請從 Kaggle 下載並放到 data/raw/" in message
    assert KAGGLE_URL in message


def test_unparsable_file_raises_validation_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(DataValidationError):
        load_raw_csv(empty)


def test_sample_loads_and_cleans(sample_csv: Path) -> None:
    cleaned, report = prepare_frame(load_raw_csv(sample_csv))
    assert report.rows == 120
    assert report.total_charges_blank == 3
    assert report.total_charges_blank_with_zero_tenure == 3  # AC-4.3：空白列 tenure 皆為 0
    assert "customerID" not in cleaned.columns  # AC-4.7
    assert cleaned["Churn"].isin([0, 1]).all()


def test_structure_errors_become_validation_errors(sample_csv: Path) -> None:
    raw = load_raw_csv(sample_csv)
    with pytest.raises(DataValidationError, match="Contract"):
        prepare_frame(raw.drop(columns=["Contract"]))
    with pytest.raises(DataValidationError, match=r"Contract.*Three year"):
        prepare_frame(raw.assign(Contract="Three year"))
    with pytest.raises(DataValidationError, match="Churn"):
        prepare_frame(raw.drop(columns=["Churn"]))
    with pytest.raises(DataValidationError, match="Churn"):
        prepare_frame(raw.assign(Churn="Maybe"))
    with pytest.raises(DataValidationError, match="SeniorCitizen"):
        prepare_frame(raw.assign(SeniorCitizen=2))
    with pytest.raises(DataValidationError, match="MonthlyCharges"):
        prepare_frame(raw.assign(MonthlyCharges=[None, *raw["MonthlyCharges"].iloc[1:]]))


def _labels(n: int = 200, churn_rate: float = 0.3) -> np.ndarray:
    y = np.zeros(n, dtype=np.int64)
    y[: int(n * churn_rate)] = 1
    return np.random.default_rng(0).permutation(y)


def test_split_is_disjoint_complete_and_stratified() -> None:  # AC-4.4
    y = _labels()
    split = split_indices(y, seed=42)
    parts = [split.train, split.validation, split.test]

    assert len(split.test) == 40  # 20%
    assert len(split.validation) == 32  # 剩餘 160 的 20%
    assert len(split.train) == 128
    assert set(split.train).isdisjoint(split.validation)
    assert set(split.train).isdisjoint(split.test)
    assert set(split.validation).isdisjoint(split.test)
    assert sorted(np.concatenate(parts).tolist()) == list(range(200))
    for part in parts:  # 分層：每份的流失比例都接近 30%
        assert abs(y[part].mean() - 0.3) <= 0.03


def test_split_is_deterministic_and_seed_dependent() -> None:
    y = _labels()
    first, second, other = (split_indices(y, seed=s) for s in (42, 42, 7))
    assert first.test.tolist() == second.test.tolist()
    assert first.test.tolist() != other.test.tolist()
    assert isinstance(first, Split)


def test_train_config_validation() -> None:
    assert TrainConfig().seed == 42
    assert TrainConfig().imbalance_strategy == "threshold_tuning"
    assert TrainConfig().to_dict()["data_path"].endswith("WA_Fn-UseC_-Telco-Customer-Churn.csv")  # type: ignore[attr-defined]
    for bad in ({"epochs": 0}, {"target_recall": 0.0}, {"target_recall": 1.5}, {"test_size": 1.0}):
        with pytest.raises(ValueError):
            TrainConfig(**bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        TrainConfig(imbalance_strategy="bogus")  # type: ignore[arg-type]
