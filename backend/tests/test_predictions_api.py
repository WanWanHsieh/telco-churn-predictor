"""POST /api/v1/predictions：成功、確定性、估算、422 各種非法輸入、503。"""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from churn_core.examples import LOW_RISK_EXAMPLE

URL = "/api/v1/predictions"
RESPONSE_KEYS = {
    "probability",
    "risk_level",
    "risk_thresholds",
    "model",
    "total_charges",
    "top_factors",
    "explanation",
}
INTERNAL_NAME_PATTERN = re.compile(r"[A-Za-z]+=|Month-to-month|Fiber optic|No internet service")


@pytest.fixture
def client(make_client: Callable[..., TestClient], artifact_dir: Path) -> TestClient:
    return make_client(model_dir=artifact_dir)


def test_success_response_matches_contract(
    client: TestClient, record: Callable[..., dict[str, Any]]
) -> None:
    response = client.post(URL, json=record())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == RESPONSE_KEYS
    assert 0 <= body["probability"] <= 1
    assert body["probability"] == round(body["probability"], 3)
    assert body["risk_level"] in {"low", "medium", "high"}
    assert body["risk_thresholds"] == {"medium": 0.3, "high": 0.6}
    assert set(body["model"]) == {"name", "display_name", "version", "trained_at"}
    assert body["model"]["name"] == "keras_mlp"
    assert body["total_charges"] == {"value": 100.0, "is_estimated": True}
    assert set(body["explanation"]) == {"method", "baseline_probability"}
    assert body["explanation"]["method"] == "integrated_gradients"
    assert response.headers["x-request-id"]


def test_top_factors_exactly_five_sorted_no_internal_names(
    client: TestClient, record: Callable[..., dict[str, Any]]
) -> None:
    factors = client.post(URL, json=record()).json()["top_factors"]
    assert len(factors) == 5
    assert all(set(f) == {"feature", "label", "direction", "impact"} for f in factors)
    magnitudes = [abs(f["impact"]) for f in factors]
    assert magnitudes == sorted(magnitudes, reverse=True)
    for factor in factors:
        assert "：" in factor["label"]
        assert not INTERNAL_NAME_PATTERN.search(factor["label"])
        expected = "increase" if factor["impact"] > 0 else "decrease"
        assert factor["direction"] == expected
        assert factor["impact"] == round(factor["impact"], 3)


def test_same_input_twice_is_identical(
    client: TestClient, record: Callable[..., dict[str, Any]]
) -> None:
    """AC-1.11、2.4：機率與因素（含順序）完全相同。"""
    first = client.post(URL, json=record()).json()
    second = client.post(URL, json=record()).json()
    assert first == second


def test_low_risk_example_with_explicit_total_charges(client: TestClient) -> None:
    body = client.post(URL, json=dict(LOW_RISK_EXAMPLE)).json()
    assert body["total_charges"] == {"value": 2100.0, "is_estimated": False}  # AC-1.15


def test_omitted_null_and_explicit_total_charges_give_same_prediction(
    client: TestClient, record: Callable[..., dict[str, Any]]
) -> None:
    """AC-1.14、1.16：省略／null 與手填估算值（10 × 50 = 500）預測相同，旗標不同。"""
    base = {"tenure": 10, "MonthlyCharges": 50.0}
    omitted = client.post(URL, json=record(**base)).json()
    null = client.post(URL, json=record(**base, TotalCharges=None)).json()
    explicit = client.post(URL, json=record(**base, TotalCharges=500)).json()

    assert omitted == null
    assert omitted["total_charges"] == {"value": 500.0, "is_estimated": True}
    assert explicit["total_charges"] == {"value": 500.0, "is_estimated": False}
    assert omitted["probability"] == explicit["probability"]
    assert [f["feature"] for f in omitted["top_factors"]] == [
        f["feature"] for f in explicit["top_factors"]
    ]


@pytest.mark.parametrize(
    ("overrides", "value", "estimated"),
    [
        ({"TotalCharges": 1200.005}, 1200.01, False),
        ({"tenure": 1, "MonthlyCharges": 20.005}, 20.01, True),
        ({"tenure": 72, "MonthlyCharges": 138.88}, 9999.36, True),  # 估算值剛好在上限內
        ({"tenure": 72, "MonthlyCharges": 200, "TotalCharges": 10000}, 10000.0, False),
        ({"MonthlyCharges": 100}, 100.0, True),  # 整數月費可接受
    ],
)
def test_total_charges_value_is_what_was_used(
    client: TestClient,
    record: Callable[..., dict[str, Any]],
    overrides: dict[str, Any],
    value: float,
    estimated: bool,
) -> None:
    body = client.post(URL, json=record(**overrides)).json()
    assert body["total_charges"] == {"value": value, "is_estimated": estimated}


def _details(response: Any) -> list[dict[str, Any]]:
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "probability" not in response.text
    details: list[dict[str, Any]] = error["details"]
    return details


@pytest.mark.parametrize(
    ("overrides", "field", "etype"),
    [
        ({"Contract": "Monthly"}, "Contract", "invalid_choice"),
        ({"Contract": "month-to-month"}, "Contract", "invalid_choice"),  # 大小寫須一致
        ({"gender": " Female"}, "gender", "invalid_choice"),  # 不自動去空白
        ({"gender": None}, "gender", "invalid_choice"),
        ({"PaymentMethod": 3}, "PaymentMethod", "invalid_choice"),
        ({"tenure": "10"}, "tenure", "invalid_type"),
        ({"tenure": 10.5}, "tenure", "invalid_type"),
        ({"tenure": 10.0}, "tenure", "invalid_type"),
        ({"tenure": True}, "tenure", "invalid_type"),
        ({"tenure": None}, "tenure", "invalid_type"),
        ({"tenure": -1}, "tenure", "out_of_range"),
        ({"tenure": 73}, "tenure", "out_of_range"),
        ({"SeniorCitizen": True}, "SeniorCitizen", "invalid_type"),
        ({"SeniorCitizen": 1.0}, "SeniorCitizen", "invalid_type"),
        ({"SeniorCitizen": "0"}, "SeniorCitizen", "invalid_type"),
        ({"SeniorCitizen": 2}, "SeniorCitizen", "invalid_choice"),
        ({"SeniorCitizen": -1}, "SeniorCitizen", "invalid_choice"),
        ({"MonthlyCharges": "100"}, "MonthlyCharges", "invalid_type"),
        ({"MonthlyCharges": True}, "MonthlyCharges", "invalid_type"),
        ({"MonthlyCharges": -0.01}, "MonthlyCharges", "out_of_range"),
        ({"MonthlyCharges": 200.01}, "MonthlyCharges", "out_of_range"),
        ({"TotalCharges": "abc"}, "TotalCharges", "invalid_type"),
        ({"TotalCharges": "500"}, "TotalCharges", "invalid_type"),
        ({"TotalCharges": True}, "TotalCharges", "invalid_type"),
        ({"TotalCharges": -1}, "TotalCharges", "out_of_range"),
        ({"TotalCharges": 10000.01}, "TotalCharges", "out_of_range"),
        ({"Typo": 1}, "Typo", "extra_field"),
        ({"customerID": "X"}, "customerID", "extra_field"),  # 單筆不接受 customerID
        ({"PhoneService": "No"}, "MultipleLines", "inconsistent"),
        (
            {"PhoneService": "Yes", "MultipleLines": "No phone service"},
            "MultipleLines",
            "inconsistent",
        ),
        ({"InternetService": "No"}, "OnlineSecurity", "inconsistent"),
        (
            {"InternetService": "DSL", "TechSupport": "No internet service"},
            "TechSupport",
            "inconsistent",
        ),
    ],
)
def test_invalid_input_returns_422_naming_the_field(
    client: TestClient,
    record: Callable[..., dict[str, Any]],
    overrides: dict[str, Any],
    field: str,
    etype: str,
) -> None:
    details = _details(client.post(URL, json=record(**overrides)))
    matched = [d for d in details if d["field"] == field]
    assert matched, details
    assert matched[0]["type"] == etype
    assert matched[0]["row"] is None
    assert matched[0]["reason"]  # 繁中原因


def test_missing_required_fields_each_reported(
    client: TestClient, record: Callable[..., dict[str, Any]]
) -> None:
    details = _details(client.post(URL, json=record(DROP=["tenure", "Contract", "gender"])))
    assert {d["field"]: d["type"] for d in details} == {
        "tenure": "missing",
        "Contract": "missing",
        "gender": "missing",
    }


def test_all_errors_listed_not_just_first(
    client: TestClient, record: Callable[..., dict[str, Any]]
) -> None:
    body = record(Contract="x", tenure=10.5, MonthlyCharges="y", Typo=1, DROP=["gender"])
    details = _details(client.post(URL, json=body))
    assert {d["field"] for d in details} == {
        "Contract",
        "tenure",
        "MonthlyCharges",
        "Typo",
        "gender",
    }


def test_estimate_over_limit_is_422_on_total_charges(
    client: TestClient, record: Callable[..., dict[str, Any]]
) -> None:
    """tenure=72、MonthlyCharges=200 → 估算 14,400.00 > 10,000（design.md 6.2）。"""
    for body in (
        record(tenure=72, MonthlyCharges=200.0),
        record(tenure=72, MonthlyCharges=200.0, TotalCharges=None),
        record(tenure=72, MonthlyCharges=138.89),  # 72 × 138.89 = 10000.08
    ):
        details = _details(client.post(URL, json=body))
        assert len(details) == 1
        assert details[0]["field"] == "TotalCharges"
        assert details[0]["type"] == "out_of_range"
        assert details[0]["row"] is None
    first = _details(client.post(URL, json=record(tenure=72, MonthlyCharges=200.0)))[0]
    assert first["reason"] == "累計費用估算值為 14,400.00，超過上限 10,000，請手動填寫累計費用"


def test_estimate_error_not_reported_when_inputs_already_invalid(
    client: TestClient, record: Callable[..., dict[str, Any]]
) -> None:
    details = _details(client.post(URL, json=record(tenure=99, MonthlyCharges=200.0)))
    assert [d["field"] for d in details] == ["tenure"]


def test_invalid_json_and_non_object_body(client: TestClient) -> None:
    broken = client.post(URL, content="{oops", headers={"Content-Type": "application/json"})
    assert _details(broken)[0]["reason"] == "請求內容不是有效的 JSON"
    nan = client.post(
        URL,
        content='{"tenure": NaN}',
        headers={"Content-Type": "application/json"},
    )
    assert any(d["field"] == "tenure" for d in _details(nan))
    assert _details(client.post(URL, json=[1, 2]))[0]["reason"] == "請求內容需為 JSON 物件"


@pytest.mark.parametrize("field", ["MonthlyCharges", "TotalCharges"])
def test_nan_and_infinity_rejected(
    client: TestClient, record: Callable[..., dict[str, Any]], field: str
) -> None:
    import json

    for literal in ("NaN", "Infinity", "-Infinity"):
        body = json.dumps(record()).replace('"MonthlyCharges": 100.0', f'"{field}": {literal}')
        response = client.post(URL, content=body, headers={"Content-Type": "application/json"})
        assert response.status_code == 422


def test_model_unavailable_returns_503(
    make_client: Callable[..., TestClient], tmp_path: Path, record: Callable[..., dict[str, Any]]
) -> None:
    client = make_client(model_dir=tmp_path / "missing")
    response = client.post(URL, json=record())
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "MODEL_UNAVAILABLE"
    assert set(error) == {"code", "message", "details", "meta", "request_id"}
    assert "probability" not in response.text


def test_corrupt_model_marks_unavailable_and_still_starts(
    make_client: Callable[..., TestClient],
    artifact_dir: Path,
    rewrite_manifest: Callable[[Path], Any],
    record: Callable[..., dict[str, Any]],
) -> None:
    (artifact_dir / "churn_mlp.keras").write_bytes(b"garbage")
    rewrite_manifest(artifact_dir)
    client = make_client(model_dir=artifact_dir)
    assert client.get("/api/v1/health").status_code == 503
    assert client.post(URL, json=record()).status_code == 503
    assert client.get("/api/v1/meta").status_code == 200


def test_get_not_allowed(client: TestClient) -> None:
    response = client.get(URL)
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
