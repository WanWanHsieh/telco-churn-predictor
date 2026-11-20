import math

import numpy as np
import pandas as pd
import pytest

from churn_core.imputation import (
    EstimateOverLimitError,
    estimate_single,
    estimate_total_charges,
    estimated_over_limit,
    impute_total_charges,
    round_half_up_2,
)


def test_estimates_tenure_times_monthly_charges() -> None:
    frame = pd.DataFrame({"tenure": [10], "MonthlyCharges": [50.0], "TotalCharges": [np.nan]})
    result, flags = impute_total_charges(frame)

    assert result["TotalCharges"].tolist() == [500.0]
    assert flags.tolist() == [True]


def test_filled_values_are_not_estimated() -> None:
    frame = pd.DataFrame(
        {
            "tenure": [10, 0, 7],
            "MonthlyCharges": [50.0, 20.0, 10.0],
            "TotalCharges": [1200.0, np.nan, np.nan],
        },
        index=[5, 6, 7],
    )
    result, flags = impute_total_charges(frame)

    assert result["TotalCharges"].tolist() == [1200.0, 0.0, 70.0]
    assert flags.tolist() == [False, True, True]
    assert result.index.tolist() == [5, 6, 7]
    assert flags.index.tolist() == [5, 6, 7]


def test_missing_total_charges_column_means_all_estimated() -> None:
    frame = pd.DataFrame({"tenure": [1, 2], "MonthlyCharges": [30.0, 40.0]})
    result, flags = impute_total_charges(frame)

    assert result["TotalCharges"].tolist() == [30.0, 80.0]
    assert flags.all()


def test_input_not_modified() -> None:
    frame = pd.DataFrame({"tenure": [10], "MonthlyCharges": [50.0], "TotalCharges": [np.nan]})
    impute_total_charges(frame)
    assert frame["TotalCharges"].isna().all()


def test_estimate_is_rounded_to_cents() -> None:
    value, estimated = estimate_single(3, 50.1, None)
    assert estimated is True
    assert value == 150.3  # 3 * 50.1 = 150.29999999999998，取到分


@pytest.mark.parametrize(
    ("tenure", "monthly", "total", "expected", "flag"),
    [
        (10, 50.0, None, 500.0, True),  # AC-1.14
        (10, 50.0, 1200.0, 1200.0, False),  # AC-1.15
        (0, 80.0, None, 0.0, True),
        (10, 50.0, 0.0, 0.0, False),  # 明確填 0 不算缺值
    ],
)
def test_estimate_single(
    tenure: int, monthly: float, total: float | None, expected: float, flag: bool
) -> None:
    assert estimate_single(tenure, monthly, total) == (expected, flag)


def test_omitted_equals_manual_estimated_value() -> None:
    omitted, _ = estimate_single(7, 33.3, None)
    manual, flag = estimate_single(7, 33.3, omitted)
    assert manual == omitted
    assert flag is False


# ---- half-up 四捨五入（design.md 6.2；AC-1.17）
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.005, 0.01),
        (0.015, 0.02),
        (0.025, 0.03),  # half-even 會得到 0.02
        (1.005, 1.01),  # 浮點內部為 1.00499999...，以 str 表示法進位
        (2.675, 2.68),
        (1200.005, 1200.01),
        (1200.004, 1200.0),
        (0.0, 0.0),
        (10_000.0, 10_000.0),
    ],
)
def test_round_half_up_2(value: float, expected: float) -> None:
    assert round_half_up_2(value) == expected


def test_round_half_up_2_non_finite_passthrough() -> None:
    assert math.isnan(round_half_up_2(math.nan))
    assert round_half_up_2(math.inf) == math.inf


def test_manual_total_charges_is_rounded_half_up() -> None:  # AC-1.17
    assert estimate_single(10, 50.0, 1200.005) == (1200.01, False)


def test_estimate_is_rounded_half_up() -> None:  # AC-1.17
    assert estimate_single(1, 20.005, None) == (20.01, True)


def test_estimate_product_is_exact_decimal_not_float() -> None:
    # 浮點 3 * 0.075 = 0.22499999999999998，若先浮點相乘再進位會錯成 0.22
    assert 3 * 0.075 != 0.225
    assert estimate_single(3, 0.075, None) == (0.23, True)
    assert estimate_total_charges(3, 0.415) == 1.25
    assert math.isnan(estimate_total_charges(math.nan, 1.0))


def test_vector_version_matches_scalar_version() -> None:
    manual = [1200.005, 0.015, 2.675, np.nan, np.nan, np.nan, 5.0]
    frame = pd.DataFrame(
        {
            "tenure": [1, 1, 1, 3, 3, 0, 4],
            "MonthlyCharges": [10.0, 10.0, 10.0, 0.075, 0.415, 80.0, 19.99],
            "TotalCharges": manual,
        }
    )
    result, flags = impute_total_charges(frame)
    expected = [
        round_half_up_2(m) if not np.isnan(m) else estimate_total_charges(t, mc)
        for m, t, mc in zip(manual, frame["tenure"], frame["MonthlyCharges"], strict=True)
    ]
    assert result["TotalCharges"].tolist() == expected
    assert flags.tolist() == [False, False, False, True, True, True, False]


# ---- 估算值上限（design.md 6.2）
def test_estimate_over_limit_raises_with_reason() -> None:
    with pytest.raises(EstimateOverLimitError) as info:
        estimate_single(72, 200.0, None)
    error = info.value
    assert error.estimate == 14400.0
    assert error.field == "TotalCharges"
    assert error.type == "out_of_range"
    assert error.reason == "累計費用估算值為 14,400.00，超過上限 10,000，請手動填寫累計費用"
    assert str(error) == error.reason
    assert isinstance(error, ValueError)


def test_estimate_limit_boundary_uses_rounded_value() -> None:
    assert estimate_single(50, 200.0, None) == (10_000.0, True)  # 剛好 10,000 可
    with pytest.raises(EstimateOverLimitError):
        estimate_single(72, 138.89, None)  # 10000.08
    assert estimate_single(72, 138.88, None) == (9999.36, True)


def test_manual_values_are_not_limit_checked_by_imputation() -> None:
    # 手填值的範圍由 schema.validate_record 負責；估算上限只針對估算值
    assert estimate_single(1, 1.0, 20_000.0) == (20_000.0, False)


def test_frame_version_does_not_raise_but_flags_over_limit() -> None:
    frame = pd.DataFrame(
        {
            "tenure": [72, 72, 100],
            "MonthlyCharges": [200.0, 200.0, 200.0],
            "TotalCharges": [np.nan, 15000.0, np.nan],
        }
    )
    result = impute_total_charges(frame)  # 訓練路徑：不檢查上限
    assert result.frame["TotalCharges"].tolist() == [14400.0, 15000.0, 20000.0]
    assert estimated_over_limit(result).tolist() == [True, False, True]
