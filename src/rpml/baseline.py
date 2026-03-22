"""
Baseline algorithms for debt repayment strategies.

The paper uses one greedy repayment algorithm and changes only the ordering of
loans:
- Debt Avalanche / HInterest: highest ordinary interest first
- Debt Snowball / Snow: smallest balance first
- Debt Average / Ave: highest average of ordinary and default rates first
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np

from .data_loader import RiosSolisInstance

EPS = 1e-6


@dataclass
class BaselineSolution:
    """Solution from a baseline algorithm."""

    payments: np.ndarray  # shape (n, T)
    balances: np.ndarray  # shape (n, T)
    savings: np.ndarray  # shape (T,)
    total_cost: float
    strategy_name: str


def _credit_card_range(instance: RiosSolisInstance) -> range:
    start = instance.n_cars + instance.n_houses
    stop = start + instance.n_credit_cards
    return range(start, stop)


def _is_credit_card(instance: RiosSolisInstance, loan_idx: int) -> bool:
    return loan_idx in _credit_card_range(instance)


def _current_balance(
    instance: RiosSolisInstance,
    balances: np.ndarray,
    loan_idx: int,
    month_idx: int,
) -> float:
    release_month = instance.release_time[loan_idx]
    if month_idx < release_month:
        return 0.0
    if month_idx == release_month:
        return float(instance.principals[loan_idx])
    return float(max(0.0, balances[loan_idx, month_idx - 1]))


def _payoff_amount(
    instance: RiosSolisInstance,
    balances: np.ndarray,
    loan_idx: int,
    month_idx: int,
) -> float:
    balance = _current_balance(instance, balances, loan_idx, month_idx)
    release_month = instance.release_time[loan_idx]
    if month_idx == release_month:
        return balance
    return balance * (1.0 + instance.interest_rates[loan_idx, month_idx])


def _payoff_amount_with_penalty(
    instance: RiosSolisInstance,
    balances: np.ndarray,
    loan_idx: int,
    month_idx: int,
) -> float:
    base_payoff = _payoff_amount(instance, balances, loan_idx, month_idx)
    if not _is_credit_card(instance, loan_idx):
        contractual = float(instance.fixed_payment[loan_idx])
        if base_payoff > contractual + EPS:
            penalty = float(instance.prepay_penalty[loan_idx])
            if penalty < 1e11:
                return base_payoff + penalty
    return base_payoff


def _minimum_required_payment(
    instance: RiosSolisInstance,
    balances: np.ndarray,
    loan_idx: int,
    month_idx: int,
) -> float:
    release_month = instance.release_time[loan_idx]
    if month_idx <= release_month:
        return 0.0

    if _is_credit_card(instance, loan_idx):
        previous_balance = max(0.0, balances[loan_idx, month_idx - 1])
        interest = instance.interest_rates[loan_idx, month_idx]
        return float(instance.min_payment_pct[loan_idx] * previous_balance * (1.0 + interest))

    contractual_payment = float(instance.fixed_payment[loan_idx])
    return max(0.0, contractual_payment)


def _max_total_payment_this_month_non_cc_prohibited(
    instance: RiosSolisInstance,
    balances: np.ndarray,
    loan_idx: int,
    month_idx: int,
    payments: np.ndarray,
) -> float:
    """
    For non-credit-card loans with prohibited prepayment, MILP enforces X <= Z * E
    per month (contractual payment). Baseline must use the same cap so totals are
    comparable to the paper model.
    """
    if _is_credit_card(instance, loan_idx):
        return float("inf")
    if instance.is_prepayment_allowed(loan_idx):
        return float("inf")
    payoff = _payoff_amount(instance, balances, loan_idx, month_idx)
    contractual = float(instance.fixed_payment[loan_idx])
    cap_total = min(payoff, contractual)
    return max(0.0, cap_total - payments[loan_idx, month_idx])


def _apply_month_update(
    instance: RiosSolisInstance,
    payments: np.ndarray,
    balances: np.ndarray,
    month_idx: int,
) -> None:
    for loan_idx in range(instance.n):
        release_month = instance.release_time[loan_idx]
        if month_idx < release_month:
            continue

        payment = payments[loan_idx, month_idx]
        base_payoff = _payoff_amount(instance, balances, loan_idx, month_idx)
        
        # Add prepayment penalty if triggered
        penalty_incurred = 0.0
        if not _is_credit_card(instance, loan_idx):
            contractual = float(instance.fixed_payment[loan_idx])
            if payment > contractual + EPS:
                prepay_penalty = float(instance.prepay_penalty[loan_idx])
                if prepay_penalty < 1e11:
                    penalty_incurred = prepay_penalty

        new_balance = base_payoff + penalty_incurred - payment

        minimum_required = _minimum_required_payment(instance, balances, loan_idx, month_idx)
        actual_min_required = min(minimum_required, base_payoff)
        if payment + EPS < actual_min_required:
            default_rate = instance.default_rates[loan_idx, month_idx]
            penalty = (actual_min_required - payment) * (1.0 + default_rate)
            new_balance += penalty

        balances[loan_idx, month_idx] = max(0.0, new_balance)


def _ordered_active_loans(
    instance: RiosSolisInstance,
    balances: np.ndarray,
    month_idx: int,
    sort_key: Callable[[int, float, int], tuple],
) -> list[int]:
    active_loans: list[tuple[tuple, int]] = []
    for loan_idx in range(instance.n):
        balance = _current_balance(instance, balances, loan_idx, month_idx)
        if balance > EPS:
            active_loans.append((sort_key(loan_idx, balance, month_idx), loan_idx))

    active_loans.sort(key=lambda item: item[0])
    return [loan_idx for _, loan_idx in active_loans]


def _solve_baseline(
    instance: RiosSolisInstance,
    strategy_name: str,
    sort_key: Callable[[int, float, int], tuple],
) -> BaselineSolution:
    n = instance.n
    T = instance.T

    payments = np.zeros((n, T))
    balances = np.zeros((n, T))
    savings = np.zeros(T)

    for month_idx in range(T):
        available_budget = float(instance.monthly_income[month_idx])
        if month_idx > 0:
            available_budget += float(savings[month_idx - 1])

        ordered_loans = _ordered_active_loans(instance, balances, month_idx, sort_key)

        # Step 1 from the paper: cover minimum payments in the ordered list.
        for loan_idx in ordered_loans:
            if month_idx == instance.release_time[loan_idx]:
                continue
            payoff_amount = _payoff_amount_with_penalty(instance, balances, loan_idx, month_idx)
            min_required = _minimum_required_payment(instance, balances, loan_idx, month_idx)
            target_payment = min(min_required, payoff_amount)
            max_step1 = _max_total_payment_this_month_non_cc_prohibited(
                instance, balances, loan_idx, month_idx, payments
            )
            target_payment = min(target_payment, max_step1)

            payment = min(target_payment, available_budget)
            payments[loan_idx, month_idx] += payment
            available_budget -= payment

            if available_budget <= EPS:
                available_budget = 0.0
                break

        # Step 2 from the paper: allocate all remaining budget greedily down the
        # same ordered list until either the budget or the debts are exhausted.
        if available_budget > EPS:
            for loan_idx in ordered_loans:
                if month_idx == instance.release_time[loan_idx]:
                    continue
                payoff_amount = _payoff_amount_with_penalty(instance, balances, loan_idx, month_idx)
                remaining_to_payoff = payoff_amount - payments[loan_idx, month_idx]
                if remaining_to_payoff <= EPS:
                    continue

                max_extra = _max_total_payment_this_month_non_cc_prohibited(
                    instance, balances, loan_idx, month_idx, payments
                )
                extra_payment = min(remaining_to_payoff, max_extra, available_budget)
                payments[loan_idx, month_idx] += extra_payment
                available_budget -= extra_payment

                if available_budget <= EPS:
                    available_budget = 0.0
                    break

        _apply_month_update(instance, payments, balances, month_idx)
        savings[month_idx] = max(0.0, available_budget)

    total_cost = float(np.sum(payments))
    return BaselineSolution(
        payments=payments,
        balances=balances,
        savings=savings,
        total_cost=total_cost,
        strategy_name=strategy_name,
    )


def debt_avalanche(instance: RiosSolisInstance) -> BaselineSolution:
    """Debt Avalanche / HInterest from the paper."""

    def sort_key(loan_idx: int, balance: float, month_idx: int) -> tuple:
        return (-float(instance.interest_rates[loan_idx, month_idx]), loan_idx)

    return _solve_baseline(instance, "Debt Avalanche", sort_key)


def debt_snowball(instance: RiosSolisInstance) -> BaselineSolution:
    """Debt Snowball / Snow from the paper."""

    def sort_key(loan_idx: int, balance: float, month_idx: int) -> tuple:
        return (balance, loan_idx)

    return _solve_baseline(instance, "Debt Snowball", sort_key)


def debt_average(instance: RiosSolisInstance) -> BaselineSolution:
    """Debt Average / Ave from the paper."""

    def sort_key(loan_idx: int, balance: float, month_idx: int) -> tuple:
        avg_rate = (instance.interest_rates[loan_idx, month_idx] + instance.default_rates[loan_idx, month_idx]) / 2.0
        return (-float(avg_rate), loan_idx)

    return _solve_baseline(instance, "Debt Average", sort_key)

