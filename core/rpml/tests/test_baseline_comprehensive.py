"""Comprehensive tests for baseline strategies against the paper logic."""

import numpy as np

from rpml.baseline import debt_avalanche, debt_average, debt_snowball
from rpml.data_loader import RiosSolisInstance


def create_instance(
    *,
    principals: list[float],
    interest_rates: list[list[float]],
    default_rates: list[list[float]],
    min_payment_pcts: list[float],
    monthly_income: list[float],
    release_times: list[int],
    n_cars: int = 0,
    n_houses: int = 0,
    n_credit_cards: int = 0,
    n_bank_loans: int = 0,
    prepay_penalty: list[float] | None = None,
    stipulated_amount: list[float] | None = None,
    fixed_payment: list[float] | None = None,
) -> RiosSolisInstance:
    n = len(principals)
    T = len(monthly_income)
    return RiosSolisInstance(
        name="test_instance",
        n=n,
        T=T,
        n_cars=n_cars,
        n_houses=n_houses,
        n_credit_cards=n_credit_cards,
        n_bank_loans=n_bank_loans,
        principals=np.array(principals, dtype=float),
        interest_rates=np.array(interest_rates, dtype=float),
        default_rates=np.array(default_rates, dtype=float),
        min_payment_pct=np.array(min_payment_pcts, dtype=float),
        prepay_penalty=np.array(prepay_penalty or [0.0] * n, dtype=float),
        monthly_income=np.array(monthly_income, dtype=float),
        release_time=np.array(release_times, dtype=int),
        stipulated_amount=np.array(stipulated_amount or [0.0] * n, dtype=float),
        fixed_payment=np.array(fixed_payment or [0.0] * n, dtype=float),
    )


def test_avalanche_waterfalls_remaining_budget_across_multiple_loans():
    instance = create_instance(
        principals=[50.0, 80.0, 100.0],
        interest_rates=[[0.30, 0.30], [0.20, 0.20], [0.10, 0.10]],
        default_rates=[[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
        min_payment_pcts=[0.0, 0.0, 0.0],
        monthly_income=[0.0, 120.0],
        release_times=[0, 0, 0],
        n_credit_cards=3,
    )

    solution = debt_avalanche(instance)
    assert np.allclose(solution.payments[:, 0], [0.0, 0.0, 0.0])
    assert np.allclose(solution.payments[:, 1], [65.0, 55.0, 0.0])
    assert np.allclose(solution.balances[:, 1], [0.0, 41.0, 110.0])
    assert solution.savings[0] == 0.0
    assert solution.savings[1] == 0.0


def test_snowball_prioritizes_smallest_balance_not_highest_rate():
    instance = create_instance(
        principals=[300.0, 100.0],
        interest_rates=[[0.30, 0.30], [0.05, 0.05]],
        default_rates=[[0.0, 0.0], [0.0, 0.0]],
        min_payment_pcts=[0.0, 0.0],
        monthly_income=[0.0, 80.0],
        release_times=[0, 0],
        n_credit_cards=2,
    )

    avalanche = debt_avalanche(instance)
    snowball = debt_snowball(instance)
    assert np.allclose(avalanche.payments[:, 0], [0.0, 0.0])
    assert np.allclose(snowball.payments[:, 0], [0.0, 0.0])
    assert np.allclose(avalanche.payments[:, 1], [80.0, 0.0])
    assert np.allclose(snowball.payments[:, 1], [0.0, 80.0])


def test_average_uses_mean_of_ordinary_and_default_rates():
    instance = create_instance(
        principals=[100.0, 100.0],
        interest_rates=[[0.10, 0.10], [0.20, 0.20]],
        default_rates=[[0.50, 0.50], [0.20, 0.20]],
        min_payment_pcts=[0.0, 0.0],
        monthly_income=[0.0, 50.0],
        release_times=[0, 0],
        n_credit_cards=2,
    )

    average_solution = debt_average(instance)
    avalanche_solution = debt_avalanche(instance)
    assert np.allclose(average_solution.payments[:, 1], [50.0, 0.0])
    assert np.allclose(avalanche_solution.payments[:, 1], [0.0, 50.0])


def test_insufficient_budget_covers_minimums_in_priority_order():
    instance = create_instance(
        principals=[100.0, 100.0],
        interest_rates=[[0.20, 0.20], [0.10, 0.10]],
        default_rates=[[0.0, 0.0], [0.0, 0.0]],
        min_payment_pcts=[0.20, 0.20],
        monthly_income=[0.0, 30.0],
        release_times=[0, 0],
        n_credit_cards=2,
    )

    solution = debt_avalanche(instance)

    # t=0: no budget, both balances remain at principal.
    assert np.allclose(solution.balances[:, 0], [100.0, 100.0])

    # t=1:
    # Loan 0 min = 100 * 1.20 * 0.20 = 24
    # Loan 1 min = 100 * 1.10 * 0.20 = 22
    # With budget 30, the paper algorithm pays minimums in priority order:
    # first 24 to loan 0, then 6 to loan 1.
    assert np.allclose(solution.payments[:, 1], [24.0, 6.0])


def test_non_credit_card_uses_fixed_payment_for_minimum_obligation():
    instance = create_instance(
        principals=[1000.0],
        interest_rates=[[0.10, 0.10]],
        default_rates=[[0.50, 0.50]],
        min_payment_pcts=[0.20],
        monthly_income=[0.0, 60.0],
        release_times=[0],
        n_cars=1,
        fixed_payment=[40.0],
    )

    solution = debt_avalanche(instance)
    assert abs(solution.balances[0, 0] - 1000.0) < 1e-6
    assert abs(solution.balances[0, 1] - (1000.0 * 1.10 - 60.0)) < 1e-6


def test_credit_card_minimum_uses_balance_with_interest():
    instance = create_instance(
        principals=[1000.0],
        interest_rates=[[0.10, 0.10, 0.10]],
        default_rates=[[0.50, 0.50, 0.50]],
        min_payment_pcts=[0.10],
        monthly_income=[0.0, 50.0, 100.0],
        release_times=[0],
        n_credit_cards=1,
    )

    solution = debt_avalanche(instance)
    assert abs(solution.balances[0, 0] - 1000.0) < 1e-6
    payoff_m1 = 1000.0 * 1.10
    min_m1 = 0.10 * 1000.0 * 1.10
    expected_balance_m1 = payoff_m1 - 50.0 + (min_m1 - 50.0) * 1.50
    assert abs(solution.balances[0, 1] - expected_balance_m1) < 1e-6
    b1 = expected_balance_m1
    payoff_m2 = b1 * 1.10
    min_m2 = 0.10 * b1 * 1.10
    expected_balance_m2 = payoff_m2 - 100.0 + (min_m2 - 100.0) * 1.50
    assert abs(solution.balances[0, 2] - expected_balance_m2) < 1e-6


def test_budget_carries_to_savings_after_payoff():
    instance = create_instance(
        principals=[100.0],
        interest_rates=[[0.05, 0.05, 0.05]],
        default_rates=[[0.0, 0.0, 0.0]],
        min_payment_pcts=[0.0],
        monthly_income=[200.0, 200.0, 200.0],
        release_times=[0],
        n_credit_cards=1,
    )

    solution = debt_avalanche(instance)
    assert abs(solution.payments[0, 0]) < 1e-6
    assert abs(solution.savings[0] - 200.0) < 1e-6
    assert abs(solution.payments[0, 1] - 105.0) < 1e-6
    assert abs(solution.savings[1] - 295.0) < 1e-6
    assert abs(solution.payments[0, 2]) < 1e-6
    assert abs(solution.savings[2] - 495.0) < 1e-6


def test_release_timing_keeps_future_loans_inactive():
    instance = create_instance(
        principals=[100.0, 200.0],
        interest_rates=[[0.10, 0.10, 0.10], [0.20, 0.20, 0.20]],
        default_rates=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        min_payment_pcts=[0.0, 0.0],
        monthly_income=[50.0, 50.0, 50.0],
        release_times=[0, 2],
        n_credit_cards=2,
    )

    solution = debt_avalanche(instance)
    assert abs(solution.payments[1, 0]) < 1e-6
    assert abs(solution.payments[1, 1]) < 1e-6
    assert abs(solution.balances[1, 0]) < 1e-6
    assert abs(solution.balances[1, 1]) < 1e-6
    assert solution.balances[1, 2] > 0.0


def test_no_payments_in_release_month_matches_milp():
    instance = create_instance(
        principals=[40.0, 50.0],
        interest_rates=[[0.10, 0.10], [0.10, 0.10]],
        default_rates=[[0.0, 0.0], [0.0, 0.0]],
        min_payment_pcts=[0.0, 0.0],
        monthly_income=[200.0, 200.0],
        release_times=[0, 0],
        n_credit_cards=1,
        n_cars=1,
    )
    solution = debt_avalanche(instance)
    assert abs(solution.payments[0, 0]) < 1e-9
    assert abs(solution.payments[1, 0]) < 1e-9


def test_non_cc_prohibited_prepay_caps_monthly_at_contractual():
    instance = create_instance(
        principals=[1000.0],
        interest_rates=[[0.0, 0.0, 0.0]],
        default_rates=[[0.0, 0.0, 0.0]],
        min_payment_pcts=[0.0],
        monthly_income=[0.0, 500.0, 500.0],
        release_times=[0],
        n_cars=1,
        fixed_payment=[40.0],
        prepay_penalty=[1e12],
    )
    solution = debt_avalanche(instance)
    assert abs(solution.payments[0, 0]) < 1e-9
    assert abs(solution.payments[0, 1] - 40.0) < 1e-6
    assert abs(solution.payments[0, 2] - 40.0) < 1e-6
