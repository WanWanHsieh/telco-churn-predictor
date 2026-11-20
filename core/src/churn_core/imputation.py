"""TotalCharges 缺值估算與四捨五入：全專案唯一實作（訓練、單筆 API、批次 API 都走這裡）。

規則（ADR-0003、design.md 6.2「TotalCharges 規則」）：
- 缺值時以 tenure × MonthlyCharges 估算；乘法以 Decimal 精確計算再進位，
  避免浮點乘積出現 x.xx4999… 而在進位時被錯誤捨去。
- 手填值與估算值一律 half-up 四捨五入到 2 位小數
  （`Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP)`），
  使「省略」與「手填同一個估算值」進入前處理的數值完全相同。
- 推論／驗證輸入的估算值不得超過 TotalCharges 上限（10,000）：
  `estimate_single` 拋 `EstimateOverLimitError`，`validate_record` 回報 TotalCharges 錯誤，
  批次用 `estimated_over_limit` 找出違規列。訓練資料不檢查上限。
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import NamedTuple

import numpy as np
import pandas as pd

from churn_core.schema import TOTAL_CHARGES_RANGE

_CENT = Decimal("0.01")
OVER_LIMIT_ERROR_TYPE = "out_of_range"  # 對應 API details[].type


def round_half_up_2(value: float) -> float:
    """half-up 四捨五入到 2 位小數（非有限值原樣回傳）。全專案唯一的金額進位函式。"""
    if not math.isfinite(value):
        return value
    with localcontext() as ctx:
        ctx.prec = 60
        return float(Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP))


def estimate_total_charges(tenure: float, monthly_charges: float) -> float:
    """tenure × MonthlyCharges，以 Decimal 精確相乘後 half-up 到 2 位（任一為 NaN 則回 NaN）。"""
    if not (math.isfinite(tenure) and math.isfinite(monthly_charges)):
        return math.nan
    with localcontext() as ctx:
        ctx.prec = 60
        product = Decimal(str(tenure)) * Decimal(str(monthly_charges))
        return float(product.quantize(_CENT, rounding=ROUND_HALF_UP))


def over_limit_reason(estimate: float) -> str:
    """估算值超限的繁中說明（帶出實際估算值）。"""
    limit = TOTAL_CHARGES_RANGE[1]
    return f"累計費用估算值為 {estimate:,.2f}，超過上限 {limit:,.0f}，請手動填寫累計費用"


class EstimateOverLimitError(ValueError):
    """估算累計費用（四捨五入後）超過上限。

    API 層轉成 422：`field=TotalCharges`、`type=out_of_range`、reason 取 `.reason`。
    """

    field = "TotalCharges"
    type = OVER_LIMIT_ERROR_TYPE

    def __init__(self, estimate: float) -> None:
        self.estimate = estimate
        self.reason = over_limit_reason(estimate)
        super().__init__(self.reason)


class ImputationResult(NamedTuple):
    frame: pd.DataFrame  # 補值後的新資料框（TotalCharges 為 float64，已 half-up 到 2 位）
    is_estimated: pd.Series  # 布林，與 frame 同索引；True 代表該列為估算值


def _round_series(series: pd.Series) -> pd.Series:
    """逐元素套用 `round_half_up_2`（NaN 保持 NaN），與純量版逐值相同。"""
    return series.map(lambda v: v if pd.isna(v) else round_half_up_2(float(v))).astype("float64")


def impute_total_charges(frame: pd.DataFrame) -> ImputationResult:
    """補齊 TotalCharges 並四捨五入。不修改傳入的資料框；有填值的列不會被估算。

    `frame` 需有 tenure、MonthlyCharges；TotalCharges 欄可整欄省略（視為全部缺值）。
    手填值與估算值都 half-up 到 2 位。本函式不檢查上限（訓練資料沿用），
    推論／驗證輸入請以 `estimated_over_limit` 檢查。
    """
    result = frame.copy()
    if "TotalCharges" in result.columns:
        total = pd.to_numeric(result["TotalCharges"], errors="raise").astype("float64")
    else:
        total = pd.Series(np.nan, index=result.index, dtype="float64")

    missing = total.isna()
    tenure = pd.to_numeric(result["tenure"], errors="raise").astype("float64")
    monthly = pd.to_numeric(result["MonthlyCharges"], errors="raise").astype("float64")
    estimate = pd.Series(
        [estimate_total_charges(t, m) for t, m in zip(tenure, monthly, strict=True)],
        index=result.index,
        dtype="float64",
    )
    result["TotalCharges"] = _round_series(total).where(~missing, estimate)
    return ImputationResult(result, missing.rename("total_charges_estimated"))


def estimated_over_limit(result: ImputationResult) -> pd.Series:
    """布林 Series：該列是估算值且（四捨五入後）超過 TotalCharges 上限，應視為驗證錯誤。"""
    return result.is_estimated & (result.frame["TotalCharges"] > TOTAL_CHARGES_RANGE[1])


def estimate_single(
    tenure: int, monthly_charges: float, total_charges: float | None
) -> tuple[float, bool]:
    """單筆版本：回傳（實際用於預測的 TotalCharges, 是否為估算）。

    內部呼叫同一個 `impute_total_charges`，不另寫第二份公式。
    估算值超過上限時拋 `EstimateOverLimitError`（手填值的範圍由 schema 驗證負責）。
    """
    one = pd.DataFrame(
        {"tenure": [tenure], "MonthlyCharges": [monthly_charges], "TotalCharges": [total_charges]}
    )
    result = impute_total_charges(one)
    value = float(result.frame["TotalCharges"].iloc[0])
    if bool(estimated_over_limit(result).iloc[0]):
        raise EstimateOverLimitError(value)
    return value, bool(result.is_estimated.iloc[0])
