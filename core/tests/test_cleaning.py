import pandas as pd
import pytest

from churn_core.cleaning import CleaningReport, clean_raw_frame
from churn_core.schema import FEATURES, ID_COLUMN, TARGET


def _raw_rows() -> pd.DataFrame:
    """手工合成的原始資料（欄位順序與資料集相同，含 customerID 與 Churn）。"""
    base = {
        "gender": "Female",
        "SeniorCitizen": 0,
        "Partner": "Yes",
        "Dependents": "No",
        "tenure": 5,
        "PhoneService": "No",
        "MultipleLines": "No phone service",
        "InternetService": "DSL",
        "OnlineSecurity": "No",
        "OnlineBackup": "Yes",
        "DeviceProtection": "No",
        "TechSupport": "No",
        "StreamingTV": "No",
        "StreamingMovies": "No",
        "Contract": "Month-to-month",
        "PaperlessBilling": "Yes",
        "PaymentMethod": "Electronic check",
        "MonthlyCharges": 29.85,
        "TotalCharges": "149.25",
        "Churn": "No",
    }
    rows = [
        {ID_COLUMN: "A-1", **base},
        {ID_COLUMN: "A-2", **base, "tenure": 0, "TotalCharges": " ", "Churn": "Yes"},
        {ID_COLUMN: "A-3", **base, "tenure": 0, "TotalCharges": " ", "Churn": "No"},
        {ID_COLUMN: "A-4", **base, "tenure": 12, "TotalCharges": " 358.2 ", "Gender": "x"},
        {ID_COLUMN: "A-5", **base, "tenure": 3, "TotalCharges": "", "Contract": " One year "},
    ]
    return pd.DataFrame(rows).drop(columns=["Gender"])


def test_blank_total_charges_become_nan_and_are_counted() -> None:
    cleaned, report = clean_raw_frame(_raw_rows())

    assert cleaned["TotalCharges"].isna().tolist() == [False, True, True, False, True]
    assert cleaned["TotalCharges"].dtype == "float64"
    assert cleaned["TotalCharges"].iloc[3] == pytest.approx(358.2)
    assert report == CleaningReport(
        rows=5, total_charges_blank=3, total_charges_blank_with_zero_tenure=2
    )
    assert report.to_dict() == {
        "rows": 5,
        "total_charges_blank": 3,
        "total_charges_blank_with_zero_tenure": 2,
    }


def test_output_columns_types_and_index() -> None:
    raw = _raw_rows()
    raw.index = pd.Index([10, 11, 12, 13, 14])
    cleaned, _ = clean_raw_frame(raw)

    assert list(cleaned.columns) == [*FEATURES, TARGET]
    assert ID_COLUMN not in cleaned.columns
    assert cleaned[TARGET].tolist() == [0, 1, 0, 0, 0]
    assert cleaned["tenure"].dtype == "int64"
    assert cleaned["SeniorCitizen"].dtype == "int64"
    assert cleaned["MonthlyCharges"].dtype == "float64"
    assert cleaned["Contract"].iloc[4] == "One year"  # 前後空白已去除
    assert cleaned.index.tolist() == [10, 11, 12, 13, 14]


def test_input_frame_is_not_modified() -> None:
    raw = _raw_rows()
    snapshot = raw.copy(deep=True)
    clean_raw_frame(raw)
    pd.testing.assert_frame_equal(raw, snapshot)


def test_frame_without_target_or_total_charges_column() -> None:
    raw = _raw_rows().drop(columns=[TARGET, "TotalCharges", ID_COLUMN])
    cleaned, report = clean_raw_frame(raw)

    assert TARGET not in cleaned.columns
    assert cleaned["TotalCharges"].isna().all()
    assert report.total_charges_blank == 5
    assert report.total_charges_blank_with_zero_tenure == 2


def test_numeric_total_charges_column_is_accepted() -> None:
    raw = _raw_rows()
    raw["TotalCharges"] = [1.5, None, 2.5, 3.5, None]
    cleaned, report = clean_raw_frame(raw)

    assert report.total_charges_blank == 2
    assert cleaned["TotalCharges"].iloc[0] == 1.5


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda df: df.assign(TotalCharges=["abc", "1", "1", "1", "1"]), "TotalCharges"),
        (lambda df: df.assign(Churn=["Maybe", "No", "No", "No", "No"]), "Churn"),
        (lambda df: df.drop(columns=["Contract"]), "Contract"),
        (lambda df: df.assign(tenure=[None, 1, 1, 1, 1]), "tenure"),
    ],
)
def test_invalid_data_raises_value_error(mutation, message: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match=message):
        clean_raw_frame(mutation(_raw_rows()))


@pytest.mark.parametrize(
    ("column", "values"),
    [
        ("tenure", [10.5, 1, 1, 1, 1]),
        ("tenure", ["abc", 1, 1, 1, 1]),
        ("tenure", ["10.5", "1", "1", "1", "1"]),
        ("SeniorCitizen", [0, 0, 0.7, 0, 0]),
        ("SeniorCitizen", [0, 0, None, 0, 0]),
        ("tenure", [1, 1, 1, float("inf"), 1]),
    ],
)
def test_non_integer_tenure_or_senior_citizen_is_rejected_not_truncated(
    column: str, values: list[object]
) -> None:
    raw = _raw_rows().assign(**{column: values})
    with pytest.raises(ValueError, match=column):
        clean_raw_frame(raw)


def test_error_message_includes_row_index_and_value() -> None:
    raw = _raw_rows()
    raw.index = pd.Index([100, 101, 102, 103, 104])
    raw["tenure"] = [1, 1, 10.5, 1, 1]
    with pytest.raises(ValueError, match=r"索引 102.*10\.5"):
        clean_raw_frame(raw)


def test_integer_valued_floats_and_strings_are_accepted() -> None:
    raw = _raw_rows().assign(tenure=[1.0, "2", 3, 4.0, 5], SeniorCitizen=[0.0, 1, "0", 1, 0])
    cleaned, _ = clean_raw_frame(raw)
    assert cleaned["tenure"].tolist() == [1, 2, 3, 4, 5]
    assert cleaned["SeniorCitizen"].tolist() == [0, 1, 0, 1, 0]
