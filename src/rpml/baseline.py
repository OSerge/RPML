"""
Baseline algorithms for debt repayment strategies.

Implements common heuristic approaches:
- Debt Avalanche: Pay highest interest rate first
- Debt Snowball: Pay smallest balance first
- Debt Average: Pay proportionally based on average rates
"""

from dataclasses import dataclass
from typing import Dict

import numpy as np

from .data_loader import RiosSolisInstance


@dataclass
class BaselineSolution:
    """Solution from a baseline algorithm."""
    payments: np.ndarray  # shape (n, T)
    balances: np.ndarray  # shape (n, T)
    savings: np.ndarray  # shape (T,)
    total_cost: float
    strategy_name: str


def debt_avalanche(instance: RiosSolisInstance) -> BaselineSolution:
    """
    Debt Avalanche strategy: prioritize loans with highest interest rates.

    At each month, pays minimum payments on all loans, then allocates
    remaining budget to the loan with highest current interest rate.
    When budget is insufficient, distributes proportionally.
    """
    n = instance.n
    T = instance.T

    payments = np.zeros((n, T))
    balances = np.zeros((n, T))
    savings = np.zeros(T)

    for j in range(n):
        r_j = instance.release_time[j]
        balances[j, r_j] = instance.principals[j]

    for t in range(T):
        available = instance.monthly_income[t] + (savings[t-1] if t > 0 else 0)

        active_loans = []
        for j in range(n):
            r_j = instance.release_time[j]
            # Include loans at release month (t == r_j) and after (t > r_j)
            if t >= r_j:
                # Use principal at release month, previous balance otherwise
                current_balance = instance.principals[j] if t == r_j else balances[j, t-1]
                if current_balance > 1e-6:
                    # No minimum payment required at release month
                    min_req = current_balance * instance.min_payment_pct[j] if t > r_j else 0.0
                    active_loans.append((j, instance.interest_rates[j, t], min_req, current_balance))

        active_loans.sort(key=lambda x: x[1], reverse=True)

        min_payments = np.zeros(n)
        total_min_req = sum(x[2] for x in active_loans)

        if total_min_req > available and total_min_req > 0:
            for j, rate, min_req, bal in active_loans:
                min_payments[j] = available * (min_req / total_min_req)
            remaining_budget = 0.0
        else:
            for j, rate, min_req, bal in active_loans:
                min_payments[j] = min_req
            remaining_budget = available - total_min_req

        if remaining_budget > 0 and active_loans:
            highest_j = active_loans[0][0]
            highest_balance = active_loans[0][3]
            # At release month, no interest; otherwise apply interest
            r_j = instance.release_time[highest_j]
            if t == r_j:
                max_payment = highest_balance
            else:
                max_payment = highest_balance * (1 + instance.interest_rates[highest_j, t])
            extra_payment = min(remaining_budget, max(0, max_payment - min_payments[highest_j]))
            min_payments[highest_j] += extra_payment

        for j in range(n):
            payments[j, t] = min_payments[j]

            r_j = instance.release_time[j]
            if t >= r_j:
                if t == r_j:
                    balances[j, t] = instance.principals[j] - payments[j, t]
                else:
                    balances[j, t] = balances[j, t-1] * (1 + instance.interest_rates[j, t]) - payments[j, t]

                if t > r_j:
                    min_required = instance.min_payment_pct[j] * balances[j, t-1]
                    if payments[j, t] < min_required - 1e-6:
                        penalty = (min_required - payments[j, t]) * (1 + instance.default_rates[j, t])
                        balances[j, t] += penalty

        total_payments = np.sum(payments[:, t])
        savings[t] = available - total_payments

    total_cost = np.sum(payments)
    return BaselineSolution(
        payments=payments,
        balances=balances,
        savings=savings,
        total_cost=total_cost,
        strategy_name="Debt Avalanche",
    )


def debt_snowball(instance: RiosSolisInstance) -> BaselineSolution:
    """
    Debt Snowball strategy: prioritize loans with smallest balances.
    
    At each month, pays minimum payments on all loans, then allocates
    remaining budget to the loan with smallest current balance.
    
    Args:
        instance: Problem instance
    
    Returns:
        BaselineSolution with payment schedule
    """
    n = instance.n
    T = instance.T
    
    payments = np.zeros((n, T))
    balances = np.zeros((n, T))
    savings = np.zeros(T)
    
    # Initialize balances at release times
    for j in range(n):
        r_j = instance.release_time[j]
        balances[j, r_j] = instance.principals[j]
    
    for t in range(T):
        available = instance.monthly_income[t] + (savings[t-1] if t > 0 else 0)

        active_loans = []
        for j in range(n):
            r_j = instance.release_time[j]
            # Include loans at release month (t == r_j) and after (t > r_j)
            if t >= r_j:
                # Use principal at release month, previous balance otherwise
                current_balance = instance.principals[j] if t == r_j else balances[j, t-1]
                if current_balance > 1e-6:
                    # No minimum payment required at release month
                    min_req = current_balance * instance.min_payment_pct[j] if t > r_j else 0.0
                    active_loans.append((j, current_balance, min_req))

        active_loans.sort(key=lambda x: x[1])

        min_payments = np.zeros(n)
        total_min_req = sum(x[2] for x in active_loans)

        if total_min_req > available and total_min_req > 0:
            budget_left = available
            affordable_loans = []
            for j, bal, min_req in active_loans:
                if min_req <= budget_left:
                    affordable_loans.append((j, bal, min_req))
                    budget_left -= min_req

            if affordable_loans:
                for j, bal, min_req in affordable_loans:
                    balance_with_interest = bal * (1 + instance.interest_rates[j, t]) if t > instance.release_time[j] else bal
                    if balance_with_interest <= min_req + budget_left:
                        min_payments[j] = balance_with_interest
                        budget_left -= (balance_with_interest - min_req)
                    else:
                        min_payments[j] = min_req
                if budget_left > 0 and affordable_loans:
                    smallest_j = affordable_loans[0][0]
                    smallest_bal = affordable_loans[0][1]
                    # At release month, no interest; otherwise apply interest
                    r_j_smallest = instance.release_time[smallest_j]
                    if t == r_j_smallest:
                        max_extra = smallest_bal - min_payments[smallest_j]
                    else:
                        max_extra = smallest_bal * (1 + instance.interest_rates[smallest_j, t]) - min_payments[smallest_j]
                    min_payments[smallest_j] += min(budget_left, max(0, max_extra))
                remaining_budget = 0.0
            else:
                for j, bal, min_req in active_loans:
                    min_payments[j] = available * (min_req / total_min_req)
                remaining_budget = 0.0
        else:
            for j, bal, min_req in active_loans:
                min_payments[j] = min_req
            remaining_budget = available - total_min_req

        if remaining_budget > 0 and active_loans:
            smallest_j = active_loans[0][0]
            smallest_balance = active_loans[0][1]
            # At release month, no interest; otherwise apply interest
            r_j = instance.release_time[smallest_j]
            if t == r_j:
                max_payment = smallest_balance
            else:
                max_payment = smallest_balance * (1 + instance.interest_rates[smallest_j, t])
            extra_payment = min(remaining_budget, max(0, max_payment - min_payments[smallest_j]))
            min_payments[smallest_j] += extra_payment

        for j in range(n):
            payments[j, t] = min_payments[j]

            r_j = instance.release_time[j]
            if t >= r_j:
                if t == r_j:
                    balances[j, t] = instance.principals[j] - payments[j, t]
                else:
                    balances[j, t] = balances[j, t-1] * (1 + instance.interest_rates[j, t]) - payments[j, t]

                if t > r_j:
                    min_required = instance.min_payment_pct[j] * balances[j, t-1]
                    if payments[j, t] < min_required - 1e-6:
                        penalty = (min_required - payments[j, t]) * (1 + instance.default_rates[j, t])
                        balances[j, t] += penalty

        total_payments = np.sum(payments[:, t])
        savings[t] = available - total_payments

    total_cost = np.sum(payments)
    return BaselineSolution(
        payments=payments,
        balances=balances,
        savings=savings,
        total_cost=total_cost,
        strategy_name="Debt Snowball",
    )


def debt_average(instance: RiosSolisInstance) -> BaselineSolution:
    """
    Debt Average strategy: allocate payments proportionally based on average interest rates.
    
    At each month, pays minimum payments, then allocates remaining budget
    proportionally to loans based on their average interest rates.
    
    Args:
        instance: Problem instance
    
    Returns:
        BaselineSolution with payment schedule
    """
    n = instance.n
    T = instance.T
    
    payments = np.zeros((n, T))
    balances = np.zeros((n, T))
    savings = np.zeros(T)
    
    # Calculate average interest rates for each loan
    avg_rates = np.mean(instance.interest_rates, axis=1)
    
    # Initialize balances
    for j in range(n):
        r_j = instance.release_time[j]
        balances[j, r_j] = instance.principals[j]
    
    # Process each month
    for t in range(T):
        available = instance.monthly_income[t] + (savings[t-1] if t > 0 else 0)
        
        # Get active loans sorted by average rate (descending)
        active_loans = []
        for j in range(n):
            r_j = instance.release_time[j]
            if t > r_j and balances[j, t-1] > 1e-6:
                min_req = instance.min_payment_pct[j] * balances[j, t-1]
                active_loans.append((j, avg_rates[j], min_req))
        
        # Sort by average rate descending
        active_loans.sort(key=lambda x: x[1], reverse=True)
        
        # Allocate budget: first pay minimums in priority order
        min_payments = np.zeros(n)
        budget_left = available
        
        for j, rate, min_req in active_loans:
            payment = min(min_req, budget_left)
            min_payments[j] = payment
            budget_left -= payment
        
        remaining_budget = budget_left
        
        # Allocate remaining budget proportionally based on average rates
        active_loan_indices = [item[0] for item in active_loans]
        if remaining_budget > 0 and active_loan_indices:
            active_rates = avg_rates[active_loan_indices]
            total_rate = np.sum(active_rates)
            
            if total_rate > 0:
                for idx, j in enumerate(active_loan_indices):
                    proportion = active_rates[idx] / total_rate
                    max_payment = balances[j, t-1] * (1 + instance.interest_rates[j, t])
                    extra_payment = min(remaining_budget * proportion, max(0, max_payment - min_payments[j]))
                    min_payments[j] += extra_payment
                    remaining_budget -= extra_payment
        
        # Apply payments
        for j in range(n):
            payments[j, t] = min_payments[j]
            
            r_j = instance.release_time[j]
            if t >= r_j:
                if t == r_j:
                    # No interest in release month (per Rios-Solis)
                    balances[j, t] = instance.principals[j] - payments[j, t]
                else:
                    balances[j, t] = balances[j, t-1] * (1 + instance.interest_rates[j, t]) - payments[j, t]
                
                # Apply penalties if underpaid (only for t > r_j)
                if t > r_j:
                    min_required = instance.min_payment_pct[j] * balances[j, t-1]
                    if payments[j, t] < min_required - 1e-6:
                        penalty = (min_required - payments[j, t]) * (1 + instance.default_rates[j, t])
                        balances[j, t] += penalty
        
        total_payments = np.sum(payments[:, t])
        savings[t] = available - total_payments
    
    # Total cost = sum of all payments
    total_cost = np.sum(payments)
    
    return BaselineSolution(
        payments=payments,
        balances=balances,
        savings=savings,
        total_cost=total_cost,
        strategy_name="Debt Average",
    )

