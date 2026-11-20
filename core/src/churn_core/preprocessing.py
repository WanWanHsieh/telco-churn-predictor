"""前處理：one-hot（類別清單固定來自 schema）＋ SeniorCitizen 直通 ＋ 數值標準化，共 45 維。

只用 numpy／pandas；參數存 JSON（格式見 design.md 5.2），不使用 pickle。
輸出維度順序：類別 one-hot（0–40）、SeniorCitizen（41）、
tenure／MonthlyCharges／TotalCharges（42–44）。
"""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from churn_core.schema import (
    CATEGORICAL_FEATURES,
    FEATURES,
    LEGAL_VALUES,
    NUMERIC_FEATURES,
    PASSTHROUGH_FEATURES,
)

FORMAT_VERSION = 1


def _build_layout() -> tuple[list[str], dict[str, list[int]]]:
    """依 schema 產生固定的維度名稱與「原始欄位 → 維度索引」對照。"""
    names: list[str] = []
    groups: dict[str, list[int]] = {}
    for feature in CATEGORICAL_FEATURES:
        start = len(names)
        names.extend(f"{feature}={value}" for value in LEGAL_VALUES[feature])
        groups[feature] = list(range(start, len(names)))
    for feature in (*PASSTHROUGH_FEATURES, *NUMERIC_FEATURES):
        groups[feature] = [len(names)]
        names.append(feature)
    # 群組依資料集欄位順序排列（因素同分時以此順序決勝，AC-2.4）
    return names, {feature: groups[feature] for feature in FEATURES}


_FEATURE_NAMES, _FEATURE_GROUPS = _build_layout()
N_FEATURES = len(_FEATURE_NAMES)


class Preprocessor:
    """前處理器：`fit`（只學數值欄位平均與標準差）→ `transform` → `to_json`／`from_json`。"""

    def __init__(self) -> None:
        self._stats: dict[str, tuple[float, float]] | None = None

    # ------------------------------------------------------------ 唯讀屬性
    @property
    def feature_names(self) -> list[str]:
        return list(_FEATURE_NAMES)

    @property
    def feature_groups(self) -> dict[str, list[int]]:
        return {feature: list(indices) for feature, indices in _FEATURE_GROUPS.items()}

    @property
    def n_features(self) -> int:
        return N_FEATURES

    @property
    def is_fitted(self) -> bool:
        return self._stats is not None

    # ------------------------------------------------------------ fit
    def fit(self, frame: pd.DataFrame) -> Preprocessor:
        """以訓練資料擬合數值欄位的平均與標準差（母體標準差，ddof=0；標準差為 0 時改用 1.0）。"""
        if len(frame) == 0:
            raise ValueError("無法以空資料擬合前處理器")
        stats: dict[str, tuple[float, float]] = {}
        for feature in NUMERIC_FEATURES:
            values = self._numeric_column(frame, feature)
            mean = float(values.mean())
            std = float(values.std(ddof=0))
            stats[feature] = (mean, std if std > 0 else 1.0)
        self._stats = stats
        return self

    # ------------------------------------------------------------ transform
    def transform(self, frame: pd.DataFrame) -> NDArray[np.float32]:
        """轉成 (n, 45) 的 float32 矩陣。未知類別、缺值、缺欄位皆拋 ValueError。

        多餘欄位（如 customerID、Churn）會被忽略。數值以 float64 計算後才轉 float32。
        """
        if self._stats is None:
            raise RuntimeError("Preprocessor 尚未 fit 或載入參數")
        missing = [f for f in FEATURES if f not in frame.columns]
        if missing:
            raise ValueError(f"缺少欄位：{', '.join(missing)}")

        out = np.zeros((len(frame), N_FEATURES), dtype=np.float64)

        for feature in CATEGORICAL_FEATURES:
            column = frame[feature].to_numpy(dtype=object)
            known = LEGAL_VALUES[feature]
            unknown = {value for value in column.tolist() if value not in known}
            if unknown:
                shown = "、".join(sorted(repr(v) for v in unknown))
                raise ValueError(f"{feature} 含有未知類別：{shown}")
            for offset, value in zip(_FEATURE_GROUPS[feature], known, strict=True):
                out[:, offset] = column == value

        for feature in PASSTHROUGH_FEATURES:
            series = frame[feature]
            if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
                raise ValueError(f"{feature} 需為數值 0 或 1")
            values = series.to_numpy(dtype=np.float64)
            if not np.isin(values, (0.0, 1.0)).all():
                raise ValueError(f"{feature} 只能是 0 或 1")
            out[:, _FEATURE_GROUPS[feature][0]] = values

        for feature in NUMERIC_FEATURES:
            mean, std = self._stats[feature]
            out[:, _FEATURE_GROUPS[feature][0]] = (
                self._numeric_column(frame, feature) - mean
            ) / std

        return out.astype(np.float32)

    @staticmethod
    def _numeric_column(frame: pd.DataFrame, feature: str) -> NDArray[np.float64]:
        if feature not in frame.columns:
            raise ValueError(f"缺少欄位：{feature}")
        try:
            values = frame[feature].to_numpy(dtype=np.float64)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{feature} 含有無法轉成數字的值") from exc
        if not np.isfinite(values).all():
            raise ValueError(f"{feature} 含有缺值或非有限數值（TotalCharges 請先估算）")
        return values

    # ------------------------------------------------------------ 序列化
    def to_dict(self) -> dict[str, Any]:
        if self._stats is None:
            raise RuntimeError("Preprocessor 尚未 fit，無法序列化")
        return {
            "format_version": FORMAT_VERSION,
            "categorical": {f: list(LEGAL_VALUES[f]) for f in CATEGORICAL_FEATURES},
            "passthrough": list(PASSTHROUGH_FEATURES),
            "numeric": {
                f: {"mean": self._stats[f][0], "std": self._stats[f][1]} for f in NUMERIC_FEATURES
            },
            "feature_names": self.feature_names,
            "feature_groups": self.feature_groups,
        }

    def to_json(self, indent: int | None = 2) -> str:
        """序列化為 JSON 字串（浮點數以 repr 輸出，往返不失真）。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Preprocessor:
        """由字典還原；格式版本、類別清單或維度配置與目前 schema 不符時拋 ValueError。"""
        try:
            if data["format_version"] != FORMAT_VERSION:
                raise ValueError(f"不支援的 format_version：{data['format_version']!r}")
            expected = {f: list(LEGAL_VALUES[f]) for f in CATEGORICAL_FEATURES}
            if data["categorical"] != expected:
                raise ValueError("preprocessor 的類別清單與 schema 不一致")
            if data["passthrough"] != list(PASSTHROUGH_FEATURES):
                raise ValueError("preprocessor 的 passthrough 欄位與 schema 不一致")
            if data["feature_names"] != _FEATURE_NAMES:
                raise ValueError("preprocessor 的 feature_names 與 schema 不一致")
            if data["feature_groups"] != _FEATURE_GROUPS:
                raise ValueError("preprocessor 的 feature_groups 與 schema 不一致")
            numeric = data["numeric"]
            stats: dict[str, tuple[float, float]] = {}
            for feature in NUMERIC_FEATURES:
                mean = float(numeric[feature]["mean"])
                std = float(numeric[feature]["std"])
                if not (math.isfinite(mean) and math.isfinite(std) and std > 0):
                    raise ValueError(f"{feature} 的 mean／std 不合法")
                stats[feature] = (mean, std)
        except (KeyError, TypeError) as exc:
            raise ValueError(f"preprocessor 內容格式錯誤：{exc!r}") from exc
        instance = cls()
        instance._stats = stats
        return instance

    @classmethod
    def from_json(cls, text: str) -> Preprocessor:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("preprocessor.json 不是合法的 JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("preprocessor.json 頂層需為物件")
        return cls.from_dict(data)
