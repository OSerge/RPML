"""Build RiosSolisInstance from Debt models or dict payloads.

Unified layer for converting app-level debt data to RPML-compatible format.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from rpml import RiosSolisInstance


PROHIBITED_PREPAYMENT = 1e12


def _get(obj, key: str, default=None):
    """Get attribute from Debt model or dict."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _annual_to_monthly_rate(annual: float) -> float:
    """Convert annual interest rate (in %) to monthly rate (decimal)."""
    return (1 + annual / 100) ** (1 / 12) - 1


def _count_debt_types(debts: list) -> dict[str, int]:
    """Count debts by type for RiosSolisInstance."""
    counts = {
        "n_cars": 0,
        "n_houses": 0,
        "n_credit_cards": 0,
        "n_bank_loans": 0,
    }
    type_mapping = {
        "car_loan": "n_cars",
        "mortgage": "n_houses",
        "credit_card": "n_credit_cards",
        "consumer_loan": "n_bank_loans",
        "microloan": "n_bank_loans",
    }
    for d in debts:
        debt_type = _get(d, "debt_type")
        if hasattr(debt_type, "value"):
            debt_type = debt_type.value
        key = type_mapping.get(debt_type, "n_bank_loans")
        counts[key] += 1
    return counts


def _get_prepay_penalty(debt) -> float:
    """Get prepayment penalty value for RPML instance."""
    prepayment_policy = _get(debt, "prepayment_policy")
    if hasattr(prepayment_policy, "value"):
        prepayment_policy = prepayment_policy.value
    
    if prepayment_policy == "prohibited":
        return PROHIBITED_PREPAYMENT
    if prepayment_policy == "with_penalty":
        pct = float(_get(debt, "prepayment_penalty_pct") or 1.0)
        return pct / 100.0
    return 0.0


def _get_min_payment_pct(debt) -> float:
    """Get minimum payment percentage based on debt type."""
    payment_type = _get(debt, "payment_type")
    if hasattr(payment_type, "value"):
        payment_type = payment_type.value
    
    if payment_type == "minimum_percent":
        return float(_get(debt, "min_payment_pct")) / 100.0
    return 0.0


def _calculate_annuity_payment(principal: float, monthly_rate: float, term_months: int) -> float:
    """Calculate annuity payment amount."""
    if monthly_rate == 0:
        return principal / term_months if term_months > 0 else principal
    return principal * (monthly_rate * (1 + monthly_rate) ** term_months) / (
        (1 + monthly_rate) ** term_months - 1
    )


def _get_fixed_payment(debt, monthly_rate: float) -> float:
    """Get fixed payment amount for installment loans."""
    fixed_payment = _get(debt, "fixed_payment")
    if fixed_payment:
        return float(fixed_payment)
    
    payment_type = _get(debt, "payment_type")
    if hasattr(payment_type, "value"):
        payment_type = payment_type.value
    
    if payment_type in ("annuity", "differentiated"):
        term = _get(debt, "term_months") or 12
        current_balance = float(_get(debt, "current_balance"))
        return _calculate_annuity_payment(current_balance, monthly_rate, term)
    return 0.0


def _min_monthly_budget(debts: list) -> float:
    """Minimum monthly budget to cover all minimum payments."""
    total = 0.0
    for d in debts:
        balance = float(_get(d, "current_balance"))
        annual_rate = float(_get(d, "interest_rate_annual"))
        monthly_rate = _annual_to_monthly_rate(annual_rate)
        
        payment_type = _get(d, "payment_type")
        if hasattr(payment_type, "value"):
            payment_type = payment_type.value
        
        if payment_type == "minimum_percent":
            min_pct = _get_min_payment_pct(d)
            total += max(balance * min_pct, balance * monthly_rate)
        else:
            total += _get_fixed_payment(d, monthly_rate)
    return total


@dataclass
class OptimizationParams:
    """Parameters for optimization run."""
    horizon_months: int = 24
    monthly_budget: float = 50000.0
    budget_by_month: Optional[list[float]] = None
    time_limit_seconds: int = 60


def build_instance(
    debts: list,
    params: OptimizationParams,
) -> RiosSolisInstance:
    """
    Build RiosSolisInstance from user debts.
    
    Args:
        debts: List of Debt models or dict payloads
        params: Optimization parameters
        
    Returns:
        RiosSolisInstance ready for RPML solver
    """
    n = len(debts)
    T = params.horizon_months

    principals = np.array([float(_get(d, "current_balance")) for d in debts])
    monthly_rates = np.array([
        _annual_to_monthly_rate(float(_get(d, "interest_rate_annual")))
        for d in debts
    ])
    interest_rates = np.tile(monthly_rates.reshape(n, 1), (1, T))

    late_fee_rates = np.array([float(_get(d, "late_fee_rate") or 0) / 100 for d in debts])
    default_rates = np.tile(late_fee_rates.reshape(n, 1), (1, T))

    min_payment_pct = np.array([_get_min_payment_pct(d) for d in debts])
    prepay_penalty = np.array([_get_prepay_penalty(d) for d in debts])

    min_budget = _min_monthly_budget(debts)
    effective_budget = max(params.monthly_budget, min_budget * 1.01)

    if params.budget_by_month and len(params.budget_by_month) >= T:
        monthly_income = np.array(
            [max(b, min_budget * 1.01) for b in params.budget_by_month[:T]]
        )
    else:
        monthly_income = np.full(T, effective_budget)

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


def compute_baseline_cost(debts: list, horizon_months: int) -> float:
    """Compute total cost if paying only minimum payments."""
    total = 0.0
    for d in debts:
        balance = float(_get(d, "current_balance"))
        annual_rate = float(_get(d, "interest_rate_annual"))
        monthly_rate = _annual_to_monthly_rate(annual_rate)
        min_pct = _get_min_payment_pct(d)
        
        payment_type = _get(d, "payment_type")
        if hasattr(payment_type, "value"):
            payment_type = payment_type.value

        for _ in range(horizon_months):
            if balance <= 0:
                break
            interest = balance * monthly_rate
            if payment_type == "minimum_percent":
                payment = max(balance * min_pct, balance + interest)
            else:
                payment = _get_fixed_payment(d, monthly_rate)
            payment = min(payment, balance + interest)
            total += payment
            balance = balance + interest - payment

        total += max(0, balance)

    return total
