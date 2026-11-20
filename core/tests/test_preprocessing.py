import copy
import json

import numpy as np
import pandas as pd
import pytest

from churn_core.examples import HIGH_RISK_EXAMPLE, LOW_RISK_EXAMPLE
from churn_core.imputation import impute_total_charges
from churn_core.preprocessing import N_FEATURES, Preprocessor
from churn_core.schema import (
    CATEGORICAL_FEATURES,
    FEATURES,
    ID_COLUMN,
    INTERNET_ADDON_FEATURES,
    LEGAL_VALUES,
)


def _training_frame() -> pd.DataFrame:
    """手工合成的小資料：兩組範例加幾列變化，已補齊 TotalCharges。"""
    rows: list[dict[str, object]] = [dict(HIGH_RISK_EXAMPLE), dict(LOW_RISK_EXAMPLE)]
    variant = dict(HIGH_RISK_EXAMPLE)
    variant.update(gender="Male", SeniorCitizen=1, tenure=24, MonthlyCharges=70.5)
    variant.update(Contract="One year", PaymentMethod="Mailed check", PhoneService="No")
    variant.update(MultipleLines="No phone service", TechSupport="Yes", TotalCharges=1500.25)
    rows.append(variant)
    frame = pd.DataFrame(rows)
    imputed, _ = impute_total_charges(frame)
    return imputed[list(FEATURES)]


def _fitted() -> Preprocessor:
    return Preprocessor().fit(_training_frame())


def test_dimension_and_feature_names() -> None:
    pre = _fitted()
    matrix = pre.transform(_training_frame())

    assert N_FEATURES == 45
    assert matrix.shape == (3, 45)
    assert matrix.dtype == np.float32
    assert len(pre.feature_names) == 45
    assert len(set(pre.feature_names)) == 45
    assert pre.feature_names[:2] == ["gender=Female", "gender=Male"]
    assert pre.feature_names[-4:] == ["SeniorCitizen", "tenure", "MonthlyCharges", "TotalCharges"]


def test_customer_id_not_in_feature_names() -> None:  # AC-4.7
    pre = _fitted()
    assert not any(ID_COLUMN.lower() in name.lower() for name in pre.feature_names)
    # 即使輸入含 customerID 與 Churn 欄，也被忽略且維度不變
    frame = _training_frame().assign(customerID=["a", "b", "c"], Churn=[1, 0, 1])
    assert pre.transform(frame).shape == (3, 45)


def test_feature_groups_cover_every_dimension_once() -> None:
    groups = Preprocessor().feature_groups
    assert list(groups) == list(FEATURES)
    flat = sorted(i for indices in groups.values() for i in indices)
    assert flat == list(range(45))
    for feature in CATEGORICAL_FEATURES:
        names = [Preprocessor().feature_names[i] for i in groups[feature]]
        assert names == [f"{feature}={v}" for v in LEGAL_VALUES[feature]]


def test_one_hot_and_passthrough_values() -> None:
    pre = _fitted()
    matrix = pre.transform(_training_frame())
    groups = pre.feature_groups

    assert matrix[0, groups["gender"]].tolist() == [1.0, 0.0]  # Female
    assert matrix[1, groups["gender"]].tolist() == [0.0, 1.0]  # Male
    assert matrix[:, groups["SeniorCitizen"][0]].tolist() == [0.0, 0.0, 1.0]
    for feature in CATEGORICAL_FEATURES:  # 每個類別欄位每列恰有一個 1
        assert (matrix[:, groups[feature]].sum(axis=1) == 1.0).all()


def test_numeric_standardization_uses_fit_statistics() -> None:
    frame = _training_frame()
    pre = Preprocessor().fit(frame)
    data = pre.to_dict()["numeric"]
    tenure = frame["tenure"].to_numpy(dtype=float)

    assert data["tenure"]["mean"] == pytest.approx(tenure.mean())
    assert data["tenure"]["std"] == pytest.approx(tenure.std())  # 母體標準差
    column = pre.transform(frame)[:, pre.feature_groups["tenure"][0]]
    assert column.astype(float) == pytest.approx((tenure - tenure.mean()) / tenure.std(), abs=1e-6)


def test_zero_std_column_does_not_divide_by_zero() -> None:
    frame = _training_frame()
    frame["MonthlyCharges"] = 50.0
    pre = Preprocessor().fit(frame)
    column = pre.transform(frame)[:, pre.feature_groups["MonthlyCharges"][0]]
    assert (column == 0.0).all()


def test_transform_twice_is_bitwise_identical() -> None:
    pre = _fitted()
    frame = _training_frame()
    assert pre.transform(frame).tobytes() == pre.transform(frame).tobytes()


def test_json_roundtrip_is_bitwise_identical() -> None:
    pre = _fitted()
    restored = Preprocessor.from_json(pre.to_json())
    frame = _training_frame()

    assert restored.transform(frame).tobytes() == pre.transform(frame).tobytes()
    assert restored.to_json() == pre.to_json()
    assert restored.feature_names == pre.feature_names
    assert restored.feature_groups == pre.feature_groups
    # 緊湊與縮排輸出皆可還原
    compact = Preprocessor.from_json(pre.to_json(indent=None))
    assert compact.transform(frame).tobytes() == pre.transform(frame).tobytes()


def test_json_structure_matches_design() -> None:
    data = json.loads(_fitted().to_json())
    assert set(data) == {
        "format_version",
        "categorical",
        "passthrough",
        "numeric",
        "feature_names",
        "feature_groups",
    }
    assert data["format_version"] == 1
    assert data["passthrough"] == ["SeniorCitizen"]
    assert list(data["numeric"]) == ["tenure", "MonthlyCharges", "TotalCharges"]
    assert set(data["numeric"]["tenure"]) == {"mean", "std"}
    assert data["categorical"]["Contract"] == ["Month-to-month", "One year", "Two year"]


def test_unknown_category_raises_value_error() -> None:
    pre = _fitted()
    frame = _training_frame()
    frame.loc[0, "Contract"] = "Three year"
    with pytest.raises(ValueError, match=r"Contract.*Three year"):
        pre.transform(frame)


@pytest.mark.parametrize("bad", [np.nan, None, "yes", "No internet service"])
def test_bad_categorical_values_raise(bad: object) -> None:
    pre = _fitted()
    frame = _training_frame()
    frame["PaperlessBilling"] = frame["PaperlessBilling"].astype(object)
    frame.loc[1, "PaperlessBilling"] = bad
    with pytest.raises(ValueError, match="PaperlessBilling"):
        pre.transform(frame)


def test_missing_column_nan_and_bad_senior_citizen_raise() -> None:
    pre = _fitted()
    frame = _training_frame()

    with pytest.raises(ValueError, match="缺少欄位"):
        pre.transform(frame.drop(columns=["tenure"]))

    nan_frame = frame.copy()
    nan_frame.loc[0, "TotalCharges"] = np.nan
    with pytest.raises(ValueError, match="TotalCharges"):
        pre.transform(nan_frame)

    text_frame = frame.copy()
    text_frame["MonthlyCharges"] = ["a", "b", "c"]
    with pytest.raises(ValueError, match="MonthlyCharges"):
        pre.transform(text_frame)

    with pytest.raises(ValueError, match="SeniorCitizen"):
        pre.transform(frame.assign(SeniorCitizen=[0, 2, 1]))
    with pytest.raises(ValueError, match="SeniorCitizen"):
        pre.transform(frame.assign(SeniorCitizen=["0", "1", "0"]))
    with pytest.raises(ValueError, match="SeniorCitizen"):
        pre.transform(frame.assign(SeniorCitizen=[False, True, False]))


def test_unfitted_use_raises() -> None:
    pre = Preprocessor()
    assert pre.is_fitted is False
    with pytest.raises(RuntimeError):
        pre.transform(_training_frame())
    with pytest.raises(RuntimeError):
        pre.to_json()
    with pytest.raises(ValueError, match="空資料"):
        pre.fit(_training_frame().iloc[0:0])
    assert _fitted().is_fitted is True


def test_from_json_rejects_tampered_content() -> None:
    good = json.loads(_fitted().to_json())

    def tampered(mutate) -> str:  # type: ignore[no-untyped-def]
        data = copy.deepcopy(good)
        mutate(data)
        return json.dumps(data)

    cases = [
        lambda d: d.update(format_version=2),
        lambda d: d["categorical"]["Contract"].reverse(),
        lambda d: d.update(passthrough=[]),
        lambda d: d["feature_names"].reverse(),
        lambda d: d["feature_groups"].update(tenure=[0]),
        lambda d: d["numeric"]["tenure"].update(std=0.0),
        lambda d: d["numeric"].pop("tenure"),
    ]
    for mutate in cases:
        with pytest.raises(ValueError):
            Preprocessor.from_json(tampered(mutate))

    with pytest.raises(ValueError, match="JSON"):
        Preprocessor.from_json("{not json")
    with pytest.raises(ValueError, match="物件"):
        Preprocessor.from_json("[]")


def test_every_legal_option_transforms() -> None:
    """每個類別欄位的每個合法值都能轉換（不含連動檢查，那是 API 層的責任）。"""
    pre = _fitted()
    base = _training_frame().iloc[[0]].reset_index(drop=True)
    for feature in (*CATEGORICAL_FEATURES,):
        for value in LEGAL_VALUES[feature]:
            row = base.copy()
            row[feature] = value
            matrix = pre.transform(row)
            hot = [
                pre.feature_names[i]
                for i in np.flatnonzero(matrix[0])
                if "=" in pre.feature_names[i]
            ]
            assert f"{feature}={value}" in hot
    assert set(INTERNET_ADDON_FEATURES) <= set(CATEGORICAL_FEATURES)
