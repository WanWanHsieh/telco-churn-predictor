"""欄位定義：19 個特徵、合法值、數值範圍、目標欄與 ID 欄。

這是前後端與訓練共用的唯一欄位定義來源（design.md 6.2）。
合法值只在下方的 Literal 型別寫一次，`LEGAL_VALUES` 由它們推導，避免兩邊不同步。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Final, Literal, get_args

# ---------------------------------------------------------------- Literal 型別
Gender = Literal["Female", "Male"]
SeniorCitizenValue = Literal[0, 1]
YesNo = Literal["Yes", "No"]
MultipleLinesValue = Literal["Yes", "No", "No phone service"]
InternetServiceValue = Literal["DSL", "Fiber optic", "No"]
InternetAddon = Literal["Yes", "No", "No internet service"]
ContractValue = Literal["Month-to-month", "One year", "Two year"]
PaymentMethodValue = Literal[
    "Electronic check",
    "Mailed check",
    "Bank transfer (automatic)",
    "Credit card (automatic)",
]

# ---------------------------------------------------------------- 欄位清單
# 資料集原始欄位順序（與 CSV 表頭、批次範本一致）
FEATURES: Final[tuple[str, ...]] = (
    "gender",
    "SeniorCitizen",
    "Partner",
    "Dependents",
    "tenure",
    "PhoneService",
    "MultipleLines",
    "InternetService",
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
    "Contract",
    "PaperlessBilling",
    "PaymentMethod",
    "MonthlyCharges",
    "TotalCharges",
)

TARGET: Final = "Churn"
ID_COLUMN: Final = "customerID"

# 6 個「無網路服務」連動欄位
INTERNET_ADDON_FEATURES: Final[tuple[str, ...]] = (
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
)

NO_PHONE_SERVICE: Final = "No phone service"
NO_INTERNET_SERVICE: Final = "No internet service"

# one-hot 的類別欄位（依資料集順序；SeniorCitizen 為 0/1 直通，不在其中）
CATEGORICAL_FEATURES: Final[tuple[str, ...]] = (
    "gender",
    "Partner",
    "Dependents",
    "PhoneService",
    "MultipleLines",
    "InternetService",
    *INTERNET_ADDON_FEATURES,
    "Contract",
    "PaperlessBilling",
    "PaymentMethod",
)
PASSTHROUGH_FEATURES: Final[tuple[str, ...]] = ("SeniorCitizen",)
NUMERIC_FEATURES: Final[tuple[str, ...]] = ("tenure", "MonthlyCharges", "TotalCharges")

# 每個類別欄位的合法值（順序即 one-hot 順序，不可隨意更動）
LEGAL_VALUES: Final[dict[str, tuple[str, ...]]] = {
    "gender": get_args(Gender),
    "Partner": get_args(YesNo),
    "Dependents": get_args(YesNo),
    "PhoneService": get_args(YesNo),
    "MultipleLines": get_args(MultipleLinesValue),
    "InternetService": get_args(InternetServiceValue),
    **{name: get_args(InternetAddon) for name in INTERNET_ADDON_FEATURES},
    "Contract": get_args(ContractValue),
    "PaperlessBilling": get_args(YesNo),
    "PaymentMethod": get_args(PaymentMethodValue),
}
SENIOR_CITIZEN_VALUES: Final[tuple[int, ...]] = get_args(SeniorCitizenValue)

# 數值欄位範圍（含端點）
TENURE_RANGE: Final = (0, 72)
MONTHLY_CHARGES_RANGE: Final = (0.0, 200.0)
TOTAL_CHARGES_RANGE: Final = (0.0, 10_000.0)
NUMERIC_RANGES: Final[dict[str, tuple[float, float]]] = {
    "tenure": (float(TENURE_RANGE[0]), float(TENURE_RANGE[1])),
    "MonthlyCharges": MONTHLY_CHARGES_RANGE,
    "TotalCharges": TOTAL_CHARGES_RANGE,
}

# 必填欄位（TotalCharges 為選填，省略或 None 時估算）
REQUIRED_FEATURES: Final[tuple[str, ...]] = tuple(f for f in FEATURES if f != "TotalCharges")
OPTIONAL_FEATURES: Final[tuple[str, ...]] = ("TotalCharges",)


def _as_finite_float(value: object) -> float | None:
    """int／float（排除 bool）且為有限值時回傳 float，否則 None。"""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def validate_record(record: Mapping[str, object]) -> list[str]:
    """檢查單筆特徵是否符合 schema，回傳所有錯誤（空清單代表通過）。

    規則與 API 的 CustomerFeatures 相同：嚴格型別、合法選項、數值範圍、
    電話／網路連動一致性、拒絕額外欄位；TotalCharges 可省略或為 None。
    """
    errors: list[str] = []

    for key in record:
        if key not in FEATURES:
            errors.append(f"{key}：不認識的欄位")
    for name in REQUIRED_FEATURES:
        if name not in record:
            errors.append(f"{name}：缺少必填欄位")

    for name in CATEGORICAL_FEATURES:
        if name in record and record[name] not in LEGAL_VALUES[name]:
            errors.append(f"{name}：不是合法選項，可用值：{'、'.join(LEGAL_VALUES[name])}")

    if "SeniorCitizen" in record:
        senior = record["SeniorCitizen"]
        if isinstance(senior, bool) or not isinstance(senior, int) or senior not in (0, 1):
            errors.append("SeniorCitizen：需為整數 0 或 1")

    if "tenure" in record:
        tenure = record["tenure"]
        low, high = TENURE_RANGE
        if isinstance(tenure, bool) or not isinstance(tenure, int) or not low <= tenure <= high:
            errors.append(f"tenure：需為 {low} 至 {high} 的整數")

    for name in ("MonthlyCharges", "TotalCharges"):
        if name not in record:
            continue
        value = record[name]
        if name == "TotalCharges" and value is None:
            continue
        low_f, high_f = NUMERIC_RANGES[name]
        number = _as_finite_float(value)
        if number is None or not low_f <= number <= high_f:
            errors.append(f"{name}：需為 {low_f:g} 至 {high_f:g} 的數字")

    errors.extend(_consistency_errors(record))
    errors.extend(_estimate_errors(record))
    return errors


def _estimate_errors(record: Mapping[str, object]) -> list[str]:
    """TotalCharges 省略／None 時，估算值（四捨五入後）也不得超過上限。

    只在 tenure、MonthlyCharges 本身合法時才檢查（否則已有各自的錯誤）。
    """
    from churn_core.imputation import EstimateOverLimitError, estimate_single  # 避免循環匯入

    if record.get("TotalCharges") is not None:
        return []
    tenure = record.get("tenure")
    monthly = _as_finite_float(record.get("MonthlyCharges"))
    if isinstance(tenure, bool) or not isinstance(tenure, int) or monthly is None:
        return []
    if not TENURE_RANGE[0] <= tenure <= TENURE_RANGE[1]:
        return []
    if not MONTHLY_CHARGES_RANGE[0] <= monthly <= MONTHLY_CHARGES_RANGE[1]:
        return []
    try:
        estimate_single(tenure, monthly, None)
    except EstimateOverLimitError as exc:
        return [f"TotalCharges：{exc.reason}"]
    return []


def _consistency_errors(record: Mapping[str, object]) -> list[str]:
    """電話／網路連動一致性（design.md 6.2）：PhoneService=No ⇔ MultipleLines=No phone service。"""
    errors: list[str] = []
    phone = record.get("PhoneService")
    lines = record.get("MultipleLines")
    phone_ok = phone in LEGAL_VALUES["PhoneService"] and lines in LEGAL_VALUES["MultipleLines"]
    if phone_ok and (phone == "No") != (lines == NO_PHONE_SERVICE):
        errors.append("MultipleLines：與 PhoneService 不一致（無電話服務時需為 No phone service）")

    internet = record.get("InternetService")
    if internet in LEGAL_VALUES["InternetService"]:
        for name in INTERNET_ADDON_FEATURES:
            value = record.get(name)
            if value in LEGAL_VALUES[name] and (internet == "No") != (value == NO_INTERNET_SERVICE):
                errors.append(
                    f"{name}：與 InternetService 不一致（無網路服務時需為 No internet service）"
                )
    return errors
