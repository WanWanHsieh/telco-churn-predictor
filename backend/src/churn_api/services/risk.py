"""機率四捨五入與風險分級（design.md 6.1、AC-5.6）。

機率先 half-up 取到 3 位小數，再以「四捨五入後」的值判定等級，
確保畫面上的「30.0%」不會被判成低風險。
"""

from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Final

from churn_api.schemas.common import RiskThresholds
from churn_api.schemas.prediction import RiskLevel

PROBABILITY_DIGITS: Final = 3


def round_half_up(value: float, digits: int = PROBABILITY_DIGITS) -> float:
    """half-up 四捨五入到 `digits` 位小數（以十進位字串表示後進位，不受二進位誤差影響）。"""
    with localcontext() as ctx:
        ctx.prec = 60
        return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), ROUND_HALF_UP))


def classify(probability: float, thresholds: RiskThresholds) -> RiskLevel:
    """依（已四捨五入的）機率分級：p < medium → low；medium <= p < high → medium；其餘 high。"""
    p = Decimal(str(probability))
    if p < Decimal(str(thresholds.medium)):
        return "low"
    if p < Decimal(str(thresholds.high)):
        return "medium"
    return "high"


def probability_and_level(raw: float, thresholds: RiskThresholds) -> tuple[float, RiskLevel]:
    """原始機率 → （3 位小數機率, 風險等級）。"""
    rounded = round_half_up(raw)
    return rounded, classify(rounded, thresholds)
