"""欄位與選項的中文名稱，以及因素顯示名稱（design.md 6.5.3 的 `top_factors[].label`）。

中文用詞與 ui.md 第 3 節表單一致。畫面上不得出現內部欄名或原始選項值（AC-2.2）。
"""

from __future__ import annotations

import math
from numbers import Integral, Real
from typing import Final

import numpy as np

from churn_core.schema import (
    FEATURES,
    INTERNET_ADDON_FEATURES,
    LEGAL_VALUES,
    SENIOR_CITIZEN_VALUES,
)

FIELD_LABELS: Final[dict[str, str]] = {
    "gender": "性別",
    "SeniorCitizen": "是否為年長者",
    "Partner": "有無配偶",
    "Dependents": "有無撫養對象",
    "tenure": "在網月數",
    "PhoneService": "電話服務",
    "MultipleLines": "多線電話",
    "InternetService": "網路服務",
    "OnlineSecurity": "線上安全服務",
    "OnlineBackup": "線上備份服務",
    "DeviceProtection": "裝置保護服務",
    "TechSupport": "技術支援服務",
    "StreamingTV": "串流電視",
    "StreamingMovies": "串流電影",
    "Contract": "合約類型",
    "PaperlessBilling": "電子帳單",
    "PaymentMethod": "付款方式",
    "MonthlyCharges": "月費",
    "TotalCharges": "累計費用",
}

_HAS_NOT: Final[dict[str | int, str]] = {"Yes": "有", "No": "無"}
_YES_NO: Final[dict[str | int, str]] = {"Yes": "是", "No": "否"}

# 類別欄位：原始值 → 中文（SeniorCitizen 的鍵為整數 0/1）
OPTION_LABELS: Final[dict[str, dict[str | int, str]]] = {
    "gender": {"Female": "女", "Male": "男"},
    "SeniorCitizen": {0: "否", 1: "是"},
    "Partner": dict(_HAS_NOT),
    "Dependents": dict(_HAS_NOT),
    "PhoneService": dict(_HAS_NOT),
    "MultipleLines": {**_HAS_NOT, "No phone service": "無電話服務"},
    "InternetService": {"DSL": "DSL", "Fiber optic": "光纖", "No": "無"},
    **{name: {**_HAS_NOT, "No internet service": "無網路服務"} for name in INTERNET_ADDON_FEATURES},
    "Contract": {"Month-to-month": "月繳", "One year": "一年約", "Two year": "兩年約"},
    "PaperlessBilling": dict(_YES_NO),
    "PaymentMethod": {
        "Electronic check": "電子支票",
        "Mailed check": "郵寄支票",
        "Bank transfer (automatic)": "銀行自動轉帳",
        "Credit card (automatic)": "信用卡自動扣款",
    },
}


def field_label(feature: str) -> str:
    """欄位中文名；未知欄位拋 ValueError。"""
    try:
        return FIELD_LABELS[feature]
    except KeyError:
        raise ValueError(f"未知的特徵欄位：{feature!r}") from None


def option_label(feature: str, value: object) -> str:
    """類別欄位的選項中文名；未知欄位或選項拋 ValueError。"""
    options = OPTION_LABELS.get(feature)
    if options is None:
        raise ValueError(f"{feature!r} 不是類別欄位")
    if _is_bool(value) or not isinstance(value, str | Integral) or value not in options:
        raise ValueError(f"{feature} 沒有選項 {value!r}")
    return options[value if isinstance(value, str) else int(value)]


def _is_bool(value: object) -> bool:
    return isinstance(value, bool | np.bool_)


def _number(feature: str, value: object) -> float:
    """接受 int／float 與 numpy 數值型別（numbers.Real），拒絕 bool。"""
    if _is_bool(value) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise ValueError(f"{feature} 需為有限數值，收到 {value!r}")
    return float(value)


def factor_label(feature: str, value: object, is_estimated: bool = False) -> str:
    """產生「欄位中文：值中文」。

    例：「合約類型：月繳」「在網月數：1 個月」「月費：$100.00」「累計費用：$100.00（估算）」。
    `is_estimated` 只對 TotalCharges 有意義，其他欄位忽略。
    """
    name = field_label(feature)
    if feature == "tenure":
        months = _number(feature, value)
        if months != int(months):
            raise ValueError(f"tenure 需為整數，收到 {value!r}")
        text = f"{int(months)} 個月"
    elif feature in ("MonthlyCharges", "TotalCharges"):
        text = f"${_number(feature, value):,.2f}"
        if feature == "TotalCharges" and is_estimated:
            text += "（估算）"
    else:
        text = option_label(feature, value)
    return f"{name}：{text}"


def _self_check() -> None:  # pragma: no cover - 匯入時確保對照表與 schema 完整
    for feature in FEATURES:
        if feature not in FIELD_LABELS:
            raise RuntimeError(f"FIELD_LABELS 缺少欄位：{feature}")
    for feature, values in LEGAL_VALUES.items():
        if set(values) != set(OPTION_LABELS[feature]):
            raise RuntimeError(f"OPTION_LABELS 與 schema 的合法值不一致：{feature}")
    if set(SENIOR_CITIZEN_VALUES) != set(OPTION_LABELS["SeniorCitizen"]):
        raise RuntimeError("OPTION_LABELS 與 schema 的 SeniorCitizen 合法值不一致")


_self_check()
