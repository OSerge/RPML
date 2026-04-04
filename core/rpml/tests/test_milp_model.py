"""Тесты MILP-модели RPML на простом примере."""

import numpy as np
import pytest

from rpml.data_loader import RiosSolisInstance
from rpml.income_monte_carlo import replace_instance_income
from rpml.milp_model import evaluate_fixed_plan_shortfalls, solve_rpml, solve_stochastic_rpml


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


def test_milp_uses_fixed_payment_for_non_credit_card_underpayment():
    """Для non-credit-card займов штраф должен опираться на fixed_payment."""
    instance = RiosSolisInstance(
        name="fixed-payment-minimum",
        n=1,
        T=3,
        n_cars=1,
        n_houses=0,
        n_credit_cards=0,
        n_bank_loans=0,
        principals=np.array([100.0]),
        interest_rates=np.zeros((1, 3)),
        default_rates=np.full((1, 3), 1.0),
        min_payment_pct=np.array([0.0]),
        prepay_penalty=np.array([0.0]),
        monthly_income=np.array([0.0, 40.0, 100.0]),
        release_time=np.array([0]),
        stipulated_amount=np.array([12.0]),
        fixed_payment=np.array([60.0]),
    )

    solution = solve_rpml(instance, time_limit_seconds=10)

    assert solution.status in ("OPTIMAL", "FEASIBLE")
    assert solution.payments[0, 1] > 0.0
    assert solution.objective_value > 100.0
    assert solution.balances[0, -1] == pytest.approx(0.0, abs=1e-3)


def test_milp_allows_activation_after_release_month():
    """Займ с release_time > 0 должен корректно активироваться после выдачи."""
    instance = RiosSolisInstance(
        name="delayed-release",
        n=1,
        T=4,
        n_cars=1,
        n_houses=0,
        n_credit_cards=0,
        n_bank_loans=0,
        principals=np.array([100.0]),
        interest_rates=np.zeros((1, 4)),
        default_rates=np.zeros((1, 4)),
        min_payment_pct=np.array([0.1]),
        prepay_penalty=np.array([0.0]),
        monthly_income=np.array([0.0, 50.0, 50.0, 50.0]),
        release_time=np.array([1]),
        stipulated_amount=np.array([12.0]),
        fixed_payment=np.array([50.0]),
    )

    solution = solve_rpml(instance, time_limit_seconds=10)

    assert solution.status in ("OPTIMAL", "FEASIBLE")
    assert solution.payments[0, 0] == pytest.approx(0.0, abs=1e-6)
    assert np.sum(solution.payments[0, 1:]) > 0.0
    assert solution.balances[0, 1] > 0.0
    assert solution.balances[0, -1] == pytest.approx(0.0, abs=1e-3)


def test_milp_solves_with_replaced_income_vector(simple_instance):
    scenario_income = np.array([180.0, 210.0, 195.0])
    scenario_instance = replace_instance_income(simple_instance, scenario_income, "smoke")

    solution = solve_rpml(scenario_instance, time_limit_seconds=10)

    assert solution.status in ("OPTIMAL", "FEASIBLE")
    assert solution.payments.shape == (scenario_instance.n, scenario_instance.T)


def test_stochastic_milp_returns_risk_metrics():
    instance = RiosSolisInstance(
        name="stochastic-simple",
        n=1,
        T=3,
        n_cars=0,
        n_houses=0,
        n_credit_cards=1,
        n_bank_loans=0,
        principals=np.array([100.0]),
        interest_rates=np.zeros((1, 3)),
        default_rates=np.zeros((1, 3)),
        min_payment_pct=np.array([0.0]),
        prepay_penalty=np.array([0.0]),
        monthly_income=np.array([0.0, 50.0, 50.0]),
        release_time=np.array([0]),
        stipulated_amount=np.array([0.0]),
        fixed_payment=np.array([0.0]),
    )
    scenario_incomes = np.array(
        [
            [0.0, 100.0, 0.0],
            [0.0, 0.0, 100.0],
        ],
        dtype=float,
    )

    solution = solve_stochastic_rpml(
        instance=instance,
        scenario_incomes=scenario_incomes,
        risk_alpha=0.95,
        risk_lambda=1.0,
        time_limit_seconds=10,
    )

    assert solution.status in ("OPTIMAL", "FEASIBLE")
    assert solution.payments.shape == (instance.n, instance.T)
    assert solution.scenario_shortfalls.shape == (scenario_incomes.shape[0], instance.T)
    assert solution.scenario_total_shortfalls.shape == (scenario_incomes.shape[0],)
    assert np.isfinite(solution.cvar_shortfall)
    assert solution.cash_shortfall_rate >= 0.0
    assert solution.cash_shortfall_rate <= 1.0


def test_stochastic_risk_lambda_reduces_or_keeps_cvar():
    instance = RiosSolisInstance(
        name="stochastic-risk-lambda",
        n=1,
        T=3,
        n_cars=0,
        n_houses=0,
        n_credit_cards=1,
        n_bank_loans=0,
        principals=np.array([100.0]),
        interest_rates=np.zeros((1, 3)),
        default_rates=np.zeros((1, 3)),
        min_payment_pct=np.array([0.0]),
        prepay_penalty=np.array([0.0]),
        monthly_income=np.array([0.0, 50.0, 50.0]),
        release_time=np.array([0]),
        stipulated_amount=np.array([0.0]),
        fixed_payment=np.array([0.0]),
    )
    scenario_incomes = np.array(
        [
            [0.0, 100.0, 0.0],
            [0.0, 0.0, 100.0],
        ],
        dtype=float,
    )

    risk_free = solve_stochastic_rpml(
        instance=instance,
        scenario_incomes=scenario_incomes,
        risk_alpha=0.95,
        risk_lambda=0.0,
        time_limit_seconds=10,
    )
    risk_aware = solve_stochastic_rpml(
        instance=instance,
        scenario_incomes=scenario_incomes,
        risk_alpha=0.95,
        risk_lambda=5.0,
        time_limit_seconds=10,
    )

    assert risk_free.status in ("OPTIMAL", "FEASIBLE")
    assert risk_aware.status in ("OPTIMAL", "FEASIBLE")
    assert risk_aware.cvar_shortfall <= risk_free.cvar_shortfall + 1e-6


def test_stochastic_shortfall_rate_beta_is_enforced():
    instance = RiosSolisInstance(
        name="stochastic-beta-feasible",
        n=1,
        T=3,
        n_cars=0,
        n_houses=0,
        n_credit_cards=1,
        n_bank_loans=0,
        principals=np.array([100.0]),
        interest_rates=np.zeros((1, 3)),
        default_rates=np.zeros((1, 3)),
        min_payment_pct=np.array([0.0]),
        prepay_penalty=np.array([0.0]),
        monthly_income=np.array([0.0, 50.0, 50.0]),
        release_time=np.array([0]),
        stipulated_amount=np.array([0.0]),
        fixed_payment=np.array([0.0]),
    )
    scenario_incomes = np.array(
        [
            [0.0, 100.0, 0.0],
            [0.0, 0.0, 100.0],
        ],
        dtype=float,
    )

    solution = solve_stochastic_rpml(
        instance=instance,
        scenario_incomes=scenario_incomes,
        risk_alpha=0.95,
        risk_lambda=1.0,
        shortfall_rate_beta=0.5,
        time_limit_seconds=10,
    )

    assert solution.status in ("OPTIMAL", "FEASIBLE")
    assert solution.shortfall_rate_beta == pytest.approx(0.5)
    assert solution.cash_shortfall_rate <= 0.5 + 1e-6


def test_stochastic_shortfall_rate_beta_can_make_model_infeasible():
    instance = RiosSolisInstance(
        name="stochastic-beta-infeasible",
        n=1,
        T=2,
        n_cars=0,
        n_houses=0,
        n_credit_cards=1,
        n_bank_loans=0,
        principals=np.array([100.0]),
        interest_rates=np.zeros((1, 2)),
        default_rates=np.zeros((1, 2)),
        min_payment_pct=np.array([0.0]),
        prepay_penalty=np.array([0.0]),
        monthly_income=np.array([0.0, 50.0]),
        release_time=np.array([0]),
        stipulated_amount=np.array([0.0]),
        fixed_payment=np.array([0.0]),
    )
    scenario_incomes = np.array(
        [
            [0.0, 100.0],
            [0.0, 0.0],
        ],
        dtype=float,
    )

    solution = solve_stochastic_rpml(
        instance=instance,
        scenario_incomes=scenario_incomes,
        risk_alpha=0.95,
        risk_lambda=1.0,
        shortfall_rate_beta=0.0,
        time_limit_seconds=10,
    )

    assert solution.status == "INFEASIBLE"


def test_evaluate_fixed_plan_shortfalls_shape_and_nonnegative(simple_instance):
    scenario_incomes = np.array(
        [
            [180.0, 210.0, 195.0],
            [120.0, 140.0, 160.0],
        ],
        dtype=float,
    )
    deterministic = solve_rpml(simple_instance, time_limit_seconds=10)

    shortfalls, totals = evaluate_fixed_plan_shortfalls(
        deterministic.payments,
        scenario_incomes,
    )

    assert shortfalls.shape == (2, simple_instance.T)
    assert totals.shape == (2,)
    assert np.all(shortfalls >= -1e-9)

