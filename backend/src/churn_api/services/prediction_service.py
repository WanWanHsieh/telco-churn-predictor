"""單筆預測 service（design.md 1.4）。

流程：估算 TotalCharges → 前處理 → 預測 → 分級 → 因素聚合排序 → 中文 label。
只依賴 `ModelRunner`、`Explainer` 兩個 Protocol 與 `churn_core`，測試時注入假物件。
"""

import logging
import time
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from churn_api.errors import AppError, ErrorCode
from churn_api.inference.artifacts import ModelDescriptor
from churn_api.inference.explainer import Explainer
from churn_api.inference.model_runner import ModelRunner
from churn_api.logging_config import log_event
from churn_api.schemas.common import ErrorDetail, ModelInfo, RiskThresholds
from churn_api.schemas.prediction import (
    CustomerFeatures,
    Explanation,
    Factor,
    PredictionResponse,
    TotalChargesInfo,
)
from churn_api.services.risk import probability_and_level, round_half_up
from churn_core.imputation import EstimateOverLimitError, estimate_single
from churn_core.labels import factor_label
from churn_core.preprocessing import Preprocessor
from churn_core.schema import FEATURES

logger = logging.getLogger("churn_api.prediction")

TOP_N = 5
_FEATURE_ORDER = {name: index for index, name in enumerate(FEATURES)}


def to_model_info(descriptor: ModelDescriptor) -> ModelInfo:
    return ModelInfo(
        name=descriptor.name,
        display_name=descriptor.display_name,
        version=descriptor.version,
        trained_at=descriptor.trained_at,
    )


def aggregate_factors(
    attribution: NDArray[np.float64],
    feature_groups: Mapping[str, list[int]],
    record: Mapping[str, Any],
    is_estimated: bool,
    top_n: int = TOP_N,
) -> list[Factor]:
    """把 45 維歸因依原始欄位加總成 19 個因素，取絕對值前 `top_n`。

    排序：`|impact|` 由大到小；相同時依 `schema.FEATURES` 固定順序，保證順序確定（AC-2.4）。
    方向：impact > 0 → increase；否則 decrease。
    """
    totals = {
        feature: float(np.sum(attribution[indices])) for feature, indices in feature_groups.items()
    }
    ranked = sorted(totals.items(), key=lambda kv: (-abs(kv[1]), _FEATURE_ORDER[kv[0]]))
    factors: list[Factor] = []
    for feature, impact in ranked[:top_n]:
        factors.append(
            Factor(
                feature=feature,
                label=factor_label(feature, record[feature], is_estimated),
                direction="increase" if impact > 0 else "decrease",
                impact=round_half_up(impact),
            )
        )
    return factors


class PredictionService:
    def __init__(
        self,
        runner: ModelRunner,
        explainer: Explainer,
        preprocessor: Preprocessor,
        model_info: ModelInfo,
        thresholds: RiskThresholds,
    ) -> None:
        self._runner = runner
        self._explainer = explainer
        self._preprocessor = preprocessor
        self._model_info = model_info
        self._thresholds = thresholds
        self._feature_groups = preprocessor.feature_groups

    def predict(self, features: CustomerFeatures) -> PredictionResponse:
        started = time.perf_counter()
        record = features.to_record()

        try:
            total_charges, is_estimated = estimate_single(
                record["tenure"], record["MonthlyCharges"], record["TotalCharges"]
            )
        except EstimateOverLimitError as exc:
            # schema 已先擋下；這裡是防線，帶出 service 提供的 reason（不需新錯誤碼）
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                details=[
                    ErrorDetail(field=exc.field, row=None, type="out_of_range", reason=exc.reason)
                ],
            ) from exc
        record["TotalCharges"] = total_charges

        frame = pd.DataFrame([record], columns=list(FEATURES))
        vector = self._preprocessor.transform(frame)  # (1, 45) float32

        raw_probability = float(self._runner.predict_proba(vector)[0])
        probability, risk_level = probability_and_level(raw_probability, self._thresholds)
        attribution = self._explainer.attribute(vector[0])
        top_factors = aggregate_factors(attribution, self._feature_groups, record, is_estimated)

        log_event(
            logger,
            logging.INFO,
            "prediction",
            "單筆預測完成",
            risk_level=risk_level,
            is_estimated=is_estimated,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return PredictionResponse(
            probability=probability,
            risk_level=risk_level,
            risk_thresholds=self._thresholds,
            model=self._model_info,
            total_charges=TotalChargesInfo(value=total_charges, is_estimated=is_estimated),
            top_factors=top_factors,
            explanation=Explanation(
                baseline_probability=round_half_up(self._explainer.baseline_probability)
            ),
        )
