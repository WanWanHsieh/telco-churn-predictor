import re

import numpy as np
import pytest

from churn_core.labels import FIELD_LABELS, OPTION_LABELS, factor_label, field_label, option_label
from churn_core.schema import FEATURES, LEGAL_VALUES, SENIOR_CITIZEN_VALUES


@pytest.mark.parametrize(
    ("feature", "value", "estimated", "expected"),
    [
        ("Contract", "Month-to-month", False, "合約類型：月繳"),
        ("Contract", "Two year", False, "合約類型：兩年約"),
        ("tenure", 1, False, "在網月數：1 個月"),
        ("tenure", 70.0, False, "在網月數：70 個月"),
        ("MonthlyCharges", 100.0, False, "月費：$100.00"),
        ("MonthlyCharges", 29.5, True, "月費：$29.50"),  # 估算旗標只影響累計費用
        ("TotalCharges", 100.0, True, "累計費用：$100.00（估算）"),
        ("TotalCharges", 2100, False, "累計費用：$2,100.00"),
        ("InternetService", "Fiber optic", False, "網路服務：光纖"),
        ("PaymentMethod", "Electronic check", False, "付款方式：電子支票"),
        ("TechSupport", "No", False, "技術支援服務：無"),
        ("TechSupport", "No internet service", False, "技術支援服務：無網路服務"),
        ("MultipleLines", "No phone service", False, "多線電話：無電話服務"),
        ("SeniorCitizen", 1, False, "是否為年長者：是"),
        ("gender", "Female", False, "性別：女"),
    ],
)
def test_factor_label_examples(feature: str, value: object, estimated: bool, expected: str) -> None:
    assert factor_label(feature, value, estimated) == expected


def test_every_legal_option_has_chinese_label_without_internal_names() -> None:
    internal = [*FEATURES, "_", "="]
    pairs = [(f, v) for f, values in LEGAL_VALUES.items() for v in values]
    pairs += [("SeniorCitizen", v) for v in SENIOR_CITIZEN_VALUES]
    assert len(pairs) == 41 + 2

    for feature, value in pairs:
        label = factor_label(feature, value)
        assert any("一" <= ch <= "鿿" for ch in label), label
        assert not any(name in label for name in internal), label
        name, _, text = label.partition("：")
        assert name == FIELD_LABELS[feature]
        assert text and text == option_label(feature, value)
        # 值的部分不可是原始英文值（DSL 為通用名稱例外）
        if value != "DSL":
            assert not re.search(r"[A-Za-z]{3,}", text), label


def test_label_tables_are_complete_and_consistent_with_schema() -> None:
    assert set(FIELD_LABELS) == set(FEATURES)
    for feature, values in LEGAL_VALUES.items():
        assert set(OPTION_LABELS[feature]) == set(values)
        assert len(set(OPTION_LABELS[feature].values())) == len(values)  # 同欄位中文選項不重複
    assert field_label("tenure") == "在網月數"


@pytest.mark.parametrize(
    ("feature", "value"),
    [
        ("nope", "x"),
        ("Contract", "Three year"),
        ("Contract", None),
        ("SeniorCitizen", True),
        ("SeniorCitizen", 2),
        ("tenure", 1.5),
        ("tenure", "1"),
        ("MonthlyCharges", float("nan")),
        ("TotalCharges", True),
    ],
)
def test_factor_label_rejects_invalid(feature: str, value: object) -> None:
    with pytest.raises(ValueError):
        factor_label(feature, value)


def test_option_label_on_non_categorical_feature_raises() -> None:
    with pytest.raises(ValueError, match="不是類別欄位"):
        option_label("tenure", 1)
    with pytest.raises(ValueError, match="未知"):
        field_label("customerID")


@pytest.mark.parametrize(
    ("feature", "value", "expected"),
    [
        ("tenure", np.int64(5), "在網月數：5 個月"),
        ("tenure", np.float64(5.0), "在網月數：5 個月"),
        ("tenure", np.int32(70), "在網月數：70 個月"),
        ("MonthlyCharges", np.float32(100.0), "月費：$100.00"),
        ("MonthlyCharges", np.int64(30), "月費：$30.00"),
        ("TotalCharges", np.float64(2100.0), "累計費用：$2,100.00"),
        ("SeniorCitizen", np.int64(1), "是否為年長者：是"),
        ("SeniorCitizen", np.int8(0), "是否為年長者：否"),
        ("Contract", np.str_("Two year"), "合約類型：兩年約"),
    ],
)
def test_factor_label_accepts_numpy_scalars(feature: str, value: object, expected: str) -> None:
    assert factor_label(feature, value) == expected


@pytest.mark.parametrize(
    ("feature", "value"),
    [
        ("SeniorCitizen", np.bool_(True)),
        ("tenure", np.bool_(True)),
        ("MonthlyCharges", np.bool_(False)),
        ("tenure", np.float64(5.5)),
        ("MonthlyCharges", np.float64("nan")),
        ("MonthlyCharges", np.float64("inf")),
    ],
)
def test_factor_label_still_rejects_numpy_bool_and_invalid(feature: str, value: object) -> None:
    with pytest.raises(ValueError):
        factor_label(feature, value)
