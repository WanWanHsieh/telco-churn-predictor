"""`GET /api/v1/meta`：前端所需設定（design.md 6.5.2）。不依賴模型是否載入。"""

from fastapi import APIRouter

from churn_api.dependencies import SettingsDep
from churn_api.schemas.common import RiskThresholds
from churn_api.schemas.meta import BatchLimits, InputRanges, MetaResponse, NumericRange
from churn_core.schema import MONTHLY_CHARGES_RANGE, TENURE_RANGE, TOTAL_CHARGES_RANGE

router = APIRouter(tags=["系統"])


def _whole(value: float) -> int | float:
    """整數值以整數輸出（0、72、200），與 design.md 6.5.2 範例一致。"""
    return int(value) if float(value).is_integer() else value


def _range(bounds: tuple[float, float]) -> NumericRange:
    return NumericRange(min=_whole(bounds[0]), max=_whole(bounds[1]))


@router.get(
    "/meta",
    response_model=MetaResponse,
    summary="前端設定",
    description="回傳風險切點、批次上傳上限與輸入欄位的合法範圍；不需要模型已載入。",
)
def get_meta(settings: SettingsDep) -> MetaResponse:
    return MetaResponse(
        risk_thresholds=RiskThresholds(
            medium=settings.risk_medium_threshold, high=settings.risk_high_threshold
        ),
        batch_limits=BatchLimits(
            max_file_bytes=settings.batch_max_file_bytes, max_rows=settings.batch_max_rows
        ),
        input_ranges=InputRanges(
            tenure=_range((float(TENURE_RANGE[0]), float(TENURE_RANGE[1]))),
            MonthlyCharges=_range(MONTHLY_CHARGES_RANGE),
            TotalCharges=_range(TOTAL_CHARGES_RANGE),
        ),
    )
