"""Adapter boundary: stable shapes/types for RiosSolisInstance -> solve_rpml -> RPMLSolution."""

import numpy as np

from rpml.data_loader import RiosSolisInstance
from rpml.milp_model import RPMLSolution, solve_rpml


def _minimal_instance() -> RiosSolisInstance:
    return RiosSolisInstance(
        name="adapter_boundary",
        n=2,
        T=3,
        n_cars=1,
        n_houses=0,
        n_credit_cards=1,
        n_bank_loans=0,
        principals=np.array([100.0, 150.0]),
        interest_rates=np.zeros((2, 3)),
        default_rates=np.zeros((2, 3)),
        min_payment_pct=np.array([0.1, 0.1]),
        prepay_penalty=np.array([0.0, 0.0]),
        monthly_income=np.array([120.0, 120.0, 120.0]),
        release_time=np.array([0, 1]),
        stipulated_amount=np.array([30.0, 20.0]),
        fixed_payment=np.array([30.0, 20.0]),
    )


def test_rpml_input_output_boundary_contract():
    instance = _minimal_instance()
    sol = solve_rpml(instance, time_limit_seconds=30)
    assert isinstance(sol, RPMLSolution)
    n, T = instance.n, instance.T
    assert sol.payments.shape == (n, T)
    assert sol.balances.shape == (n, T)
    assert sol.savings.shape == (T,)
    assert sol.active_loans.shape == (n, T)
    assert isinstance(sol.objective_value, float)
    assert isinstance(sol.solve_time, float)
    assert isinstance(sol.gap, float)
    assert isinstance(sol.status, str)
