"""MILP optimization task."""

import numpy as np
from rpml import RiosSolisInstance, solve_rpml

from app.celery_app import celery_app


def _annual_to_monthly_rate(annual: float) -> float:
    return (1 + annual / 100) ** (1 / 12) - 1


def _build_instance_from_dict(data: dict) -> RiosSolisInstance:
    debts = data["debts"]
    horizon = data.get("horizon_months", 24)
    monthly_income = data.get("monthly_income", 50000.0)

    n = len(debts)
    T = horizon

    principals = np.array([float(d["current_balance"]) for d in debts])
    monthly_rates = np.array([_annual_to_monthly_rate(float(d["interest_rate_annual"])) for d in debts])
    interest_rates = np.tile(monthly_rates.reshape(n, 1), (1, T))
    default_rates = np.zeros((n, T))
    min_payment_pct = np.array([float(d["min_payment_pct"]) / 100 for d in debts])
    prepay_penalty = np.full(n, 1e12)
    monthly_income_arr = np.full(T, float(monthly_income))
    release_time = np.zeros(n, dtype=int)
    stipulated_amount = np.zeros(n)
    fixed_payment = np.zeros(n)

    return RiosSolisInstance(
        name="user_plan",
        n=n,
        T=T,
        n_cars=0,
        n_houses=0,
        n_credit_cards=n,
        n_bank_loans=0,
        principals=principals,
        interest_rates=interest_rates,
        default_rates=default_rates,
        min_payment_pct=min_payment_pct,
        prepay_penalty=prepay_penalty,
        monthly_income=monthly_income_arr,
        release_time=release_time,
        stipulated_amount=stipulated_amount,
        fixed_payment=fixed_payment,
    )


@celery_app.task(bind=True)
def run_optimization(self, data: dict) -> dict:
    """Run RPML optimization in Celery worker."""
    instance = _build_instance_from_dict(data)
    solution = solve_rpml(instance, time_limit_seconds=60)

    debt_names = [d["name"] for d in data["debts"]]
    payments_matrix = {name: solution.payments[j, :].tolist() for j, name in enumerate(debt_names)}

    return {
        "payments_matrix": payments_matrix,
        "total_cost": float(solution.objective_value),
        "savings_vs_minimum": None,
        "status": solution.status,
        "solve_time": solution.solve_time,
    }
