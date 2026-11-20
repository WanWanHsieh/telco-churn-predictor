"""批次預測 service（design.md 6.5.5）：向量化估算與前處理、分塊推論、摘要。

不回傳因素（ui 5.1 已排除）。輸入已由 `csv_parser` 逐列驗證，這裡只做計算；
結果依檔案原始順序，同一份檔案重複處理結果完全相同（AC-6.12）。
"""

import logging
import time

import pandas as pd

from churn_api.inference.model_runner import ModelRunner
from churn_api.logging_config import log_event
from churn_api.schemas.batch import BatchResponse, BatchRow, BatchSummary
from churn_api.schemas.common import ModelInfo, RiskThresholds
from churn_api.services.csv_parser import ParsedBatch
from churn_api.services.risk import probability_and_level
from churn_core.imputation import impute_total_charges
from churn_core.preprocessing import Preprocessor
from churn_core.schema import FEATURES

logger = logging.getLogger("churn_api.batch")


class BatchService:
    def __init__(
        self,
        runner: ModelRunner,
        preprocessor: Preprocessor,
        model_info: ModelInfo,
        thresholds: RiskThresholds,
    ) -> None:
        self._runner = runner
        self._preprocessor = preprocessor
        self._model_info = model_info
        self._thresholds = thresholds

    def predict(self, batch: ParsedBatch) -> BatchResponse:
        started = time.perf_counter()
        records = [row.features.to_record() for row in batch.rows]
        frame = pd.DataFrame(records, columns=list(FEATURES))

        imputed = impute_total_charges(frame)  # 估算旗標與 half-up 2 位，與單筆同一函式
        matrix = self._preprocessor.transform(imputed.frame)
        probabilities = self._runner.predict_proba(matrix)
        estimated_flags = imputed.is_estimated.tolist()

        counts = {"low": 0, "medium": 0, "high": 0}
        results: list[BatchRow] = []
        for row, raw, estimated in zip(batch.rows, probabilities, estimated_flags, strict=True):
            probability, level = probability_and_level(float(raw), self._thresholds)
            counts[level] += 1
            results.append(
                BatchRow(
                    row=row.row,
                    customer_id=row.customer_id,
                    probability=probability,
                    risk_level=level,
                    total_charges_estimated=bool(estimated),
                    input=row.features,
                )
            )

        summary = BatchSummary(
            total=len(results),
            high=counts["high"],
            medium=counts["medium"],
            low=counts["low"],
            estimated_total_charges=sum(1 for flag in estimated_flags if flag),
        )
        # 只記列數、大小、耗時，不記內容（AC-6.11）
        log_event(
            logger,
            logging.INFO,
            "batch_prediction",
            "批次預測完成",
            rows=summary.total,
            file_bytes=batch.file_bytes,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return BatchResponse(
            summary=summary,
            risk_thresholds=self._thresholds,
            model=self._model_info,
            has_customer_id=batch.has_customer_id,
            ignored_columns=batch.ignored_columns,
            results=results,
        )
