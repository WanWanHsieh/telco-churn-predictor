"""讀檔、結構檢查與分層切分（design.md 4.2 步驟 2、3、4、6）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from sklearn.model_selection import train_test_split

from churn_core.cleaning import CleaningReport, clean_raw_frame
from churn_core.schema import (
    CATEGORICAL_FEATURES,
    LEGAL_VALUES,
    SENIOR_CITIZEN_VALUES,
    TARGET,
)
from churn_ml.config import KAGGLE_URL


class DataFileNotFoundError(Exception):
    """找不到原始資料檔；CLI 攔截後印出友善訊息、exit code 2、不印堆疊。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            "找不到資料檔，請從 Kaggle 下載並放到 data/raw/\n"
            f"下載網址：{KAGGLE_URL}\n"
            f"（目前尋找的路徑：{path}）"
        )


class DataValidationError(Exception):
    """資料結構或內容不符合預期；CLI 攔截後 exit code 2。"""


def load_raw_csv(path: Path) -> pd.DataFrame:
    """讀取原始 CSV。檔案不存在拋 `DataFileNotFoundError`，無法解析拋 `DataValidationError`。"""
    if not path.is_file():
        raise DataFileNotFoundError(path)
    try:
        return pd.read_csv(path)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise DataValidationError(f"無法解析資料檔 {path.name}：{exc}") from exc


def prepare_frame(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """清理（churn_core）並檢查結構：欄位齊全、類別值皆在合法集合內，否則 `DataValidationError`。"""
    try:
        cleaned, report = clean_raw_frame(raw)
    except ValueError as exc:
        raise DataValidationError(f"資料清理失敗：{exc}") from exc
    if TARGET not in cleaned.columns:
        raise DataValidationError(f"資料缺少目標欄位 {TARGET}")
    check_structure(cleaned)
    return cleaned, report


def check_structure(cleaned: pd.DataFrame) -> None:
    """類別欄位的值必須在 schema 合法集合內；SeniorCitizen 只能 0／1；數值欄位不可缺值。"""
    problems: list[str] = []
    for feature in CATEGORICAL_FEATURES:
        unknown = sorted({str(v) for v in cleaned[feature].unique()} - set(LEGAL_VALUES[feature]))
        if unknown:
            problems.append(f"{feature} 含有未知類別：{'、'.join(unknown)}")
    if not set(cleaned["SeniorCitizen"].unique()) <= set(SENIOR_CITIZEN_VALUES):
        problems.append("SeniorCitizen 只能是 0 或 1")
    if cleaned["MonthlyCharges"].isna().any():
        problems.append("MonthlyCharges 含有缺值")
    if problems:
        raise DataValidationError("；".join(problems))


@dataclass(frozen=True)
class Split:
    """三個互不重疊的列位置（對應清理後資料框的 `iloc`）。"""

    train: NDArray[np.int64]
    validation: NDArray[np.int64]
    test: NDArray[np.int64]


def split_indices(
    y: NDArray[np.int64],
    *,
    seed: int,
    test_size: float = 0.2,
    validation_size: float = 0.2,
) -> Split:
    """依 Churn 分層：先切出測試集（封存），剩餘部分再切出驗證集。"""
    positions = np.arange(len(y), dtype=np.int64)
    train_val, test = train_test_split(
        positions, test_size=test_size, stratify=y, random_state=seed
    )
    train, validation = train_test_split(
        train_val, test_size=validation_size, stratify=y[train_val], random_state=seed
    )
    return Split(
        train=np.sort(train).astype(np.int64),
        validation=np.sort(validation).astype(np.int64),
        test=np.sort(test).astype(np.int64),
    )
