import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from churn_core.examples import EXAMPLES, HIGH_RISK_EXAMPLE, LOW_RISK_EXAMPLE
from churn_core.imputation import estimate_single
from churn_core.schema import FEATURES, LEGAL_VALUES, REQUIRED_FEATURES, validate_record

FIXTURE = Path(__file__).parent / "fixtures" / "high_risk_example.json"


@pytest.mark.parametrize("example", [HIGH_RISK_EXAMPLE, LOW_RISK_EXAMPLE])
def test_examples_pass_schema_and_consistency(example: Mapping[str, object]) -> None:
    assert validate_record(example) == []
    assert set(REQUIRED_FEATURES) <= set(example)
    assert set(example) <= set(FEATURES)


def test_example_values_match_design_6_7() -> None:
    assert HIGH_RISK_EXAMPLE["tenure"] == 1
    assert HIGH_RISK_EXAMPLE["MonthlyCharges"] == 100.0
    assert "TotalCharges" not in HIGH_RISK_EXAMPLE  # 留空，示範估算
    assert estimate_single(1, 100.0, None) == (100.0, True)  # 估算 100.00
    assert LOW_RISK_EXAMPLE["tenure"] == 70
    assert LOW_RISK_EXAMPLE["TotalCharges"] == 2100.0
    assert LOW_RISK_EXAMPLE["InternetService"] == "No"
    assert EXAMPLES == {"high_risk": HIGH_RISK_EXAMPLE, "low_risk": LOW_RISK_EXAMPLE}


def test_high_risk_fixture_equals_examples_py() -> None:
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == HIGH_RISK_EXAMPLE


# ---- schema.validate_record 的錯誤分支（驗證檢查本身有效，避免範例測試空轉）
def _with(**changes: object) -> dict[str, object]:
    record: dict[str, object] = dict(HIGH_RISK_EXAMPLE)
    record.update(changes)
    return record


@pytest.mark.parametrize(
    ("record", "field"),
    [
        (_with(gender="female"), "gender"),
        (_with(Contract="Month-to-Month"), "Contract"),
        (_with(SeniorCitizen="0"), "SeniorCitizen"),
        (_with(SeniorCitizen=True), "SeniorCitizen"),
        (_with(SeniorCitizen=2), "SeniorCitizen"),
        (_with(tenure=10.5), "tenure"),
        (_with(tenure="10"), "tenure"),
        (_with(tenure=73), "tenure"),
        (_with(tenure=-1), "tenure"),
        (_with(MonthlyCharges=200.01), "MonthlyCharges"),
        (_with(MonthlyCharges="100"), "MonthlyCharges"),
        (_with(MonthlyCharges=float("nan")), "MonthlyCharges"),
        (_with(TotalCharges=-0.01), "TotalCharges"),
        (_with(TotalCharges=10_000.01), "TotalCharges"),
        (_with(TotalCharges="500"), "TotalCharges"),
        (_with(extra_field=1), "extra_field"),
        (_with(PhoneService="No"), "MultipleLines"),  # No 但 MultipleLines=No
        (_with(PhoneService="Yes", MultipleLines="No phone service"), "MultipleLines"),
        (_with(InternetService="No"), "OnlineSecurity"),  # No 但附加服務非 No internet service
        (_with(TechSupport="No internet service"), "TechSupport"),  # 有網路卻標無網路
    ],
)
def test_validate_record_reports_error_for_field(record: dict[str, object], field: str) -> None:
    errors = validate_record(record)
    assert any(error.startswith(f"{field}：") for error in errors), errors


def test_validate_record_missing_and_boundaries() -> None:
    missing = {k: v for k, v in HIGH_RISK_EXAMPLE.items() if k not in ("Contract", "tenure")}
    errors = validate_record(missing)
    assert sum("缺少必填欄位" in e for e in errors) == 2

    assert validate_record(_with(tenure=0, MonthlyCharges=0, TotalCharges=0)) == []
    assert validate_record(_with(tenure=72, MonthlyCharges=200, TotalCharges=10_000)) == []
    assert validate_record(_with(TotalCharges=None)) == []  # None 等同省略


def test_validate_record_lists_all_errors_not_just_first() -> None:
    assert len(validate_record(_with(gender="x", tenure=99, Contract="y"))) == 3


def test_legal_values_have_expected_shape() -> None:
    assert sum(len(v) for v in LEGAL_VALUES.values()) == 41
    assert len(LEGAL_VALUES) == 15


def test_examples_are_read_only() -> None:
    for example in (HIGH_RISK_EXAMPLE, LOW_RISK_EXAMPLE, *EXAMPLES.values()):
        with pytest.raises(TypeError):
            example["tenure"] = 99  # type: ignore[index]
    with pytest.raises(TypeError):
        EXAMPLES["x"] = {}  # type: ignore[index]
    assert HIGH_RISK_EXAMPLE["tenure"] == 1
    assert dict(HIGH_RISK_EXAMPLE) is not HIGH_RISK_EXAMPLE


def test_validate_record_rejects_estimate_over_limit() -> None:
    record = _with(tenure=72, MonthlyCharges=200.0)  # 省略 TotalCharges → 估算 14,400
    assert validate_record(record) == [
        "TotalCharges：累計費用估算值為 14,400.00，超過上限 10,000，請手動填寫累計費用"
    ]
    assert validate_record({**record, "TotalCharges": None}) == validate_record(record)


def test_validate_record_estimate_limit_edge_cases() -> None:
    assert validate_record(_with(tenure=72, MonthlyCharges=200.0, TotalCharges=9000.0)) == []
    assert validate_record(_with(tenure=50, MonthlyCharges=200.0)) == []  # 剛好 10,000
    assert validate_record(_with(tenure=72, MonthlyCharges=138.89)) != []  # 10000.08
    # tenure／MonthlyCharges 本身不合法時只報各自的錯誤，不重複報估算
    errors = validate_record(_with(tenure=73, MonthlyCharges=500.0))
    assert len(errors) == 2
    assert not any("估算" in e for e in errors)
