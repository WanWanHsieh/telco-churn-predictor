"""原始 CSV 清理：空白字串→缺值、Churn→0/1、移除 customerID，並回報清理計數。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from churn_core.schema import FEATURES, TARGET


@dataclass(frozen=True)
class CleaningReport:
    """清理報告（寫入訓練 log 與 manifest，AC-4.3）。"""

    rows: int
    total_charges_blank: int  # TotalCharges 空白或缺值的列數
    total_charges_blank_with_zero_tenure: int  # 其中 tenure=0 的列數（ADR-0003 佐證）

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _strict_int(series: pd.Series, name: str) -> pd.Series:
    """轉成 int64；缺值或非整數值（如 10.5）拋 ValueError，不做截斷。"""
    try:
        numeric = pd.to_numeric(series, errors="raise").astype("float64")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} 含有無法轉成數字的值") from exc
    bad = numeric.isna() | ~np.isfinite(numeric) | (numeric % 1 != 0)
    if bad.any():
        position = int(np.flatnonzero(bad.to_numpy())[0])
        index_label = series.index[position]
        shown_index = index_label.item() if hasattr(index_label, "item") else index_label
        shown_value = series.iloc[position]
        shown_value = shown_value.item() if hasattr(shown_value, "item") else shown_value
        raise ValueError(
            f"{name} 需為整數且不可缺值：共 {int(bad.sum())} 列不合法，"
            f"第一筆索引 {shown_index!r}，值為 {shown_value!r}"
        )
    return numeric.astype("int64")


def clean_raw_frame(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """清理原始資料框，回傳（清理後資料, 報告）。不修改傳入的資料框。

    - 所有字串欄位去除前後空白。
    - TotalCharges：空白字串（如 `" "`）視為缺值（NaN），不拋例外；
      非空白但無法轉成數字則拋 ValueError。
    - Churn（若存在）：Yes→1、No→0，其他值拋 ValueError。
    - 移除 customerID。輸出欄位順序為 FEATURES＋（Churn），索引保留原樣。
    """
    missing = [c for c in FEATURES if c not in raw.columns and c != "TotalCharges"]
    if missing:
        raise ValueError(f"原始資料缺少欄位：{', '.join(missing)}")

    frame = raw.copy()
    for column in frame.columns:
        if not pd.api.types.is_numeric_dtype(frame[column]):
            frame[column] = frame[column].map(_strip)

    # TotalCharges：空白 → NaN → float
    if "TotalCharges" in frame.columns:
        total = frame["TotalCharges"]
        blank = total.isna() | (total == "")
        try:
            converted = pd.to_numeric(total.where(~blank), errors="raise")
        except (ValueError, TypeError) as exc:
            raise ValueError("TotalCharges 含有無法轉成數字的值") from exc
        frame["TotalCharges"] = converted.astype("float64")
    else:
        blank = pd.Series(True, index=frame.index)
        frame["TotalCharges"] = pd.Series(float("nan"), index=frame.index, dtype="float64")

    frame["tenure"] = _strict_int(frame["tenure"], "tenure")
    frame["SeniorCitizen"] = _strict_int(frame["SeniorCitizen"], "SeniorCitizen")
    frame["MonthlyCharges"] = pd.to_numeric(frame["MonthlyCharges"], errors="raise").astype(
        "float64"
    )

    columns = list(FEATURES)
    if TARGET in frame.columns:
        mapped = frame[TARGET].map({"Yes": 1, "No": 0})
        if mapped.isna().any():
            raise ValueError(f"{TARGET} 含有 Yes／No 以外的值")
        frame[TARGET] = mapped.astype("int64")
        columns.append(TARGET)

    report = CleaningReport(
        rows=len(frame),
        total_charges_blank=int(blank.sum()),
        total_charges_blank_with_zero_tenure=int((blank & (frame["tenure"] == 0)).sum()),
    )
    # 只保留 FEATURES＋Churn；customerID 在此被移除
    return frame[columns], report
