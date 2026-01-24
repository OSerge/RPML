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
    
    # Process each month
    for t in range(T):
        # Calculate available budget (income + previous savings)
        available = instance.monthly_income[t] + (savings[t-1] if t > 0 else 0)
        
        # Get active loans sorted by interest rate (descending) for prioritization
        active_loans = []
        for j in range(n):
            r_j = instance.release_time[j]
            if t > r_j and balances[j, t-1] > 1e-6:  # Loan is active
                min_req = instance.min_payment_pct[j] * balances[j, t-1]
                active_loans.append((j, instance.interest_rates[j, t], min_req))
        
        # Sort by interest rate descending (Avalanche priority)
        active_loans.sort(key=lambda x: x[1], reverse=True)
        
        # Allocate budget: first pay minimums in priority order, then extra to highest rate
        min_payments = np.zeros(n)
        budget_left = available
        
        # Pay minimum payments in priority order (highest rate first)
        for j, rate, min_req in active_loans:
            payment = min(min_req, budget_left)
            min_payments[j] = payment
            budget_left -= payment
        
        remaining_budget = budget_left
        
        # Allocate remaining budget to highest interest rate loan (already sorted)
        if remaining_budget > 0 and active_loans:
            # Pay extra to highest rate loan
            highest_j = active_loans[0][0]
            max_payment = balances[highest_j, t-1] * (1 + instance.interest_rates[highest_j, t])
            extra_payment = min(remaining_budget, max(0, max_payment - min_payments[highest_j]))
            min_payments[highest_j] += extra_payment
            remaining_budget -= extra_payment
        
        # Apply payments
        for j in range(n):
            payments[j, t] = min_payments[j]
            
            # Update balances
            r_j = instance.release_time[j]
            if t >= r_j:
                if t == r_j:
                    # No interest in release month (per Rios-Solis)
                    balances[j, t] = instance.principals[j] - payments[j, t]
                else:
                    balances[j, t] = balances[j, t-1] * (1 + instance.interest_rates[j, t]) - payments[j, t]
                
                # Apply penalties if underpaid (only for t > r_j, no penalty in release month)
                if t > r_j:
                    min_required = instance.min_payment_pct[j] * balances[j, t-1]
                    if payments[j, t] < min_required - 1e-6:
                        penalty = (min_required - payments[j, t]) * (1 + instance.default_rates[j, t])
                        balances[j, t] += penalty
        
        # Remaining budget goes to savings
        total_payments = np.sum(payments[:, t])
        savings[t] = available - total_payments
    
    # Total cost = sum of all payments
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
    
    # Process each month
    for t in range(T):
        available = instance.monthly_income[t] + (savings[t-1] if t > 0 else 0)
        
        # Get active loans sorted by balance (ascending) for prioritization
        active_loans = []
        for j in range(n):
            r_j = instance.release_time[j]
            if t > r_j and balances[j, t-1] > 1e-6:
                min_req = instance.min_payment_pct[j] * balances[j, t-1]
                active_loans.append((j, balances[j, t-1], min_req))
        
        # Sort by balance ascending (Snowball priority)
        active_loans.sort(key=lambda x: x[1])
        
        # Allocate budget: first pay minimums in priority order
        min_payments = np.zeros(n)
        budget_left = available
        
        for j, bal, min_req in active_loans:
            payment = min(min_req, budget_left)
            min_payments[j] = payment
            budget_left -= payment
        
        remaining_budget = budget_left
        
        # Allocate remaining budget to smallest balance loan
        if remaining_budget > 0 and active_loans:
            smallest_j = active_loans[0][0]
            max_payment = balances[smallest_j, t-1] * (1 + instance.interest_rates[smallest_j, t])
            extra_payment = min(remaining_budget, max(0, max_payment - min_payments[smallest_j]))
            min_payments[smallest_j] += extra_payment
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

