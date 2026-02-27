"""Тесты MILP-модели RPML на простом примере."""

import numpy as np
import pytest

from rpml.data_loader import RiosSolisInstance
from rpml.milp_model import solve_rpml


@pytest.fixture
def simple_instance():
    """Простая выполнимая инстанция для проверки ограничений."""
    n = 1
    T = 3
    return RiosSolisInstance(
        name="simple",
        n=n,
        T=T,
        n_cars=1,
        n_houses=0,
        n_credit_cards=0,
        n_bank_loans=0,
        principals=np.array([100.0]),
        interest_rates=np.full((n, T), 0.01),
        default_rates=np.full((n, T), 0.1),
        min_payment_pct=np.array([0.2]),
        prepay_penalty=np.array([0.0]),
        monthly_income=np.full(T, 200.0),
        release_time=np.array([0]),
        stipulated_amount=np.array([50.0]),
        fixed_payment=np.zeros(n),
    )


def test_milp_feasible_and_respects_budget(simple_instance):
    """Модель должна быть выполнима и соблюдать бюджет/финальные балансы."""
    solution = solve_rpml(simple_instance, time_limit_seconds=10)

    assert solution.status in ("OPTIMAL", "FEASIBLE")
    assert solution.balances[0, -1] == pytest.approx(0.0, abs=1e-3)

    for t in range(simple_instance.T):
        total_payments = float(np.sum(solution.payments[:, t]))
        available = float(simple_instance.monthly_income[t] + (solution.savings[t - 1] if t > 0 else 0.0))
        used = float(total_payments + solution.savings[t])
        assert used <= available + 1e-4

