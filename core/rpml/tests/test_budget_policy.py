import numpy as np

from rpml.data_loader import RiosSolisInstance, with_budget_starts_next_month


def test_with_budget_starts_next_month_shifts_income_vector() -> None:
    instance = RiosSolisInstance(
        name="budget_policy_test",
        n=1,
        T=4,
        n_cars=0,
        n_houses=0,
        n_credit_cards=0,
        n_bank_loans=1,
        principals=np.array([100.0], dtype=float),
        interest_rates=np.zeros((1, 4), dtype=float),
        default_rates=np.zeros((1, 4), dtype=float),
        min_payment_pct=np.array([0.1], dtype=float),
        prepay_penalty=np.array([0.0], dtype=float),
        monthly_income=np.array([10.0, 20.0, 30.0, 40.0], dtype=float),
        release_time=np.array([0], dtype=int),
        stipulated_amount=np.array([1.0], dtype=float),
        fixed_payment=np.array([1.0], dtype=float),
    )
    shifted = with_budget_starts_next_month(instance)
    np.testing.assert_array_equal(shifted.monthly_income, np.array([0.0, 10.0, 20.0, 30.0], dtype=float))
