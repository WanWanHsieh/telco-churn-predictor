"""風險分級與機率四捨五入（design.md 6.1、AC-5.6）。"""

import pytest

from churn_api.schemas.common import RiskThresholds
from churn_api.services.risk import classify, probability_and_level, round_half_up

DEFAULT = RiskThresholds(medium=0.30, high=0.60)


@pytest.mark.parametrize(
    ("raw", "rounded", "level"),
    [
        (0.0, 0.0, "low"),
        (0.29, 0.29, "low"),
        (0.2994, 0.299, "low"),
        (0.2995, 0.3, "medium"),  # 0.2995 → 0.300 → medium（AC-5.6）
        (0.30, 0.3, "medium"),
        (0.59, 0.59, "medium"),
        (0.5994, 0.599, "medium"),
        (0.5995, 0.6, "high"),
        (0.60, 0.6, "high"),
        (1.0, 1.0, "high"),
    ],
)
def test_boundaries(raw: float, rounded: float, level: str) -> None:
    assert probability_and_level(raw, DEFAULT) == (rounded, level)


def test_classify_uses_rounded_value_so_30_percent_is_never_low() -> None:
    assert classify(0.3, DEFAULT) == "medium"
    assert classify(0.6, DEFAULT) == "high"


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        (0.1235, 3, 0.124),  # half-up（銀行家進位會得 0.123）
        (0.1245, 3, 0.125),
        (0.0005, 3, 0.001),
        (0.0004, 3, 0.0),
        (-0.0005, 3, -0.001),  # 影響值為負時遠離零進位
        (0.7245, 3, 0.725),
        (2.675, 2, 2.68),
    ],
)
def test_round_half_up(value: float, digits: int, expected: float) -> None:
    assert round_half_up(value, digits) == expected


def test_custom_thresholds_come_from_settings() -> None:
    custom = RiskThresholds(medium=0.25, high=0.7)
    assert classify(0.249, custom) == "low"
    assert classify(0.25, custom) == "medium"
    assert classify(0.699, custom) == "medium"
    assert classify(0.7, custom) == "high"
