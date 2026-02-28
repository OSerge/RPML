"""RPML optimizer service - wrapper over MILP model."""

from dataclasses import dataclass
from datetime import date
from typing import Optional

import numpy as np
from rpml import RiosSolisInstance, solve_rpml

from app.models.debt import Debt, DebtType, PaymentType, PrepaymentPolicy


PROHIBITED_PREPAYMENT = 1e12


def _annual_to_monthly_rate(annual: float) -> float:
    """Convert annual interest rate (in %) to monthly rate (decimal)."""
    return (1 + annual / 100) ** (1 / 12) - 1


def _count_debt_types(debts: list[Debt]) -> dict[str, int]:
    """Count debts by type for RiosSolisInstance."""
    counts = {
        "n_cars": 0,
        "n_houses": 0,
        "n_credit_cards": 0,
        "n_bank_loans": 0,
    }
    type_mapping = {
        DebtType.CAR_LOAN: "n_cars",
        DebtType.MORTGAGE: "n_houses",
        DebtType.CREDIT_CARD: "n_credit_cards",
        DebtType.CONSUMER_LOAN: "n_bank_loans",
        DebtType.MICROLOAN: "n_bank_loans",
    }
    for d in debts:
        key = type_mapping.get(d.debt_type, "n_bank_loans")
        counts[key] += 1
    return counts


def _get_prepay_penalty(debt: Debt) -> float:
    """Get prepayment penalty value for RPML instance."""
    if debt.prepayment_policy == PrepaymentPolicy.PROHIBITED:
        return PROHIBITED_PREPAYMENT
    if debt.prepayment_policy == PrepaymentPolicy.WITH_PENALTY:
        pct = float(debt.prepayment_penalty_pct or 1.0)
        return pct / 100.0
    return 0.0


def _get_min_payment_pct(debt: Debt) -> float:
    """Get minimum payment percentage based on debt type."""
    if debt.payment_type == PaymentType.MINIMUM_PERCENT:
        return float(debt.min_payment_pct) / 100.0
    return 0.0


def _calculate_annuity_payment(principal: float, monthly_rate: float, term_months: int) -> float:
    """Calculate annuity payment amount."""
    if monthly_rate == 0:
        return principal / term_months if term_months > 0 else principal
    return principal * (monthly_rate * (1 + monthly_rate) ** term_months) / (
        (1 + monthly_rate) ** term_months - 1
    )


def _get_fixed_payment(debt: Debt, monthly_rate: float) -> float:
    """Get fixed payment amount for installment loans."""
    if debt.fixed_payment:
        return float(debt.fixed_payment)
    if debt.payment_type in (PaymentType.ANNUITY, PaymentType.DIFFERENTIATED):
        term = debt.term_months or 12
        return _calculate_annuity_payment(float(debt.current_balance), monthly_rate, term)
    return 0.0


@dataclass
class OptimizationParams:
    """Parameters for optimization run."""
    horizon_months: int = 24
    monthly_budget: float = 50000.0
    budget_by_month: Optional[list[float]] = None
    time_limit_seconds: int = 60


def _build_instance(
    debts: list[Debt],
    params: OptimizationParams,
) -> RiosSolisInstance:
    """Build RiosSolisInstance from user debts."""
    n = len(debts)
    T = params.horizon_months

    principals = np.array([float(d.current_balance) for d in debts])
    monthly_rates = np.array([_annual_to_monthly_rate(float(d.interest_rate_annual)) for d in debts])
    interest_rates = np.tile(monthly_rates.reshape(n, 1), (1, T))

    late_fee_rates = np.array([float(d.late_fee_rate or 0) / 100 for d in debts])
    default_rates = np.tile(late_fee_rates.reshape(n, 1), (1, T))

    min_payment_pct = np.array([_get_min_payment_pct(d) for d in debts])
    prepay_penalty = np.array([_get_prepay_penalty(d) for d in debts])

    if params.budget_by_month and len(params.budget_by_month) >= T:
        monthly_income = np.array(params.budget_by_month[:T])
    else:
        monthly_income = np.full(T, params.monthly_budget)

    release_time = np.zeros(n, dtype=int)

    fixed_payment = np.array([
        _get_fixed_payment(d, monthly_rates[i]) for i, d in enumerate(debts)
    ])
    stipulated_amount = fixed_payment.copy()

    type_counts = _count_debt_types(debts)

    return RiosSolisInstance(
        name="user_plan",
        n=n,
        T=T,
        n_cars=type_counts["n_cars"],
        n_houses=type_counts["n_houses"],
        n_credit_cards=type_counts["n_credit_cards"],
        n_bank_loans=type_counts["n_bank_loans"],
        principals=principals,
        interest_rates=interest_rates,
        default_rates=default_rates,
        min_payment_pct=min_payment_pct,
        prepay_penalty=prepay_penalty,
        monthly_income=monthly_income,
        release_time=release_time,
        stipulated_amount=stipulated_amount,
        fixed_payment=fixed_payment,
    )


def _compute_baseline_cost(debts: list[Debt], horizon_months: int) -> float:
    """Compute total cost if paying only minimum payments."""
    total = 0.0
    for d in debts:
        balance = float(d.current_balance)
        monthly_rate = _annual_to_monthly_rate(float(d.interest_rate_annual))
        min_pct = _get_min_payment_pct(d)

        for _ in range(horizon_months):
            if balance <= 0:
                break
            interest = balance * monthly_rate
            if d.payment_type == PaymentType.MINIMUM_PERCENT:
                payment = max(balance * min_pct, balance + interest)
            else:
                payment = _get_fixed_payment(d, monthly_rate)
            payment = min(payment, balance + interest)
            total += payment
            balance = balance + interest - payment

        total += max(0, balance)

    return total


class RPMLOptimizerService:
    """Service for running RPML optimization on user debts."""

    async def optimize(
        self,
        debts: list[Debt],
        monthly_budget: float = 50000.0,
        budget_by_month: Optional[list[float]] = None,
        horizon_months: int = 24,
        time_limit_seconds: int = 60,
    ) -> dict:
        """
        Run optimization on user debts.

        Args:
            debts: List of user debts
            monthly_budget: Fixed monthly budget (used if budget_by_month not provided)
            budget_by_month: Optional list of monthly budgets
            horizon_months: Planning horizon in months
            time_limit_seconds: Solver time limit

        Returns:
            Dict with payments_matrix, total_cost, savings_vs_minimum, status, solve_time
        """
        params = OptimizationParams(
            horizon_months=horizon_months,
            monthly_budget=monthly_budget,
            budget_by_month=budget_by_month,
            time_limit_seconds=time_limit_seconds,
        )

        instance = _build_instance(debts, params)
        solution = solve_rpml(instance, time_limit_seconds=params.time_limit_seconds)

        debt_names = [d.name for d in debts]
        payments_matrix = {}
        balances_matrix = {}
        for j, name in enumerate(debt_names):
            payments_matrix[name] = solution.payments[j, :].tolist()
            balances_matrix[name] = solution.balances[j, :].tolist()

        baseline_cost = _compute_baseline_cost(debts, horizon_months)
        savings = baseline_cost - solution.objective_value if solution.objective_value < float("inf") else None

        return {
            "payments_matrix": payments_matrix,
            "balances_matrix": balances_matrix,
            "total_cost": float(solution.objective_value),
            "savings_vs_minimum": savings,
            "baseline_cost": baseline_cost,
            "status": solution.status,
            "solve_time": solution.solve_time,
            "horizon_months": horizon_months,
        }
