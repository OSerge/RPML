"""
Metrics for evaluating RPML solutions and comparing with baselines.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .baseline import BaselineSolution
from .milp_model import RPMLSolution


@dataclass
class ComparisonResult:
    """Results comparing optimal solution with baseline."""
    instance_name: str
    n_loans: int
    optimal_cost: float
    baseline_cost: float
    relative_savings: float  # Percentage
    optimal_solve_time: float
    optimal_gap: float
    optimal_status: str
    baseline_strategy: str


def relative_savings(optimal_cost: float, baseline_cost: float) -> float:
    """
    Calculate relative savings percentage.
    
    Formula: (baseline_cost - optimal_cost) / baseline_cost * 100
    
    Args:
        optimal_cost: Cost from optimal solution
        baseline_cost: Cost from baseline strategy
    
    Returns:
        Percentage savings (positive = optimal is better)
    """
    if baseline_cost <= 0:
        return 0.0
    return (baseline_cost - optimal_cost) / baseline_cost * 100.0


def compare_solutions(
    optimal: RPMLSolution,
    baseline: BaselineSolution,
    instance_name: str,
    n_loans: int,
) -> ComparisonResult:
    """
    Compare optimal MILP solution with baseline strategy.
    
    Args:
        optimal: Optimal solution from MILP solver
        baseline: Solution from baseline algorithm
        instance_name: Name of the instance
        n_loans: Number of loans in instance
    
    Returns:
        ComparisonResult with metrics
    """
    savings_pct = relative_savings(optimal.objective_value, baseline.total_cost)
    
    return ComparisonResult(
        instance_name=instance_name,
        n_loans=n_loans,
        optimal_cost=optimal.objective_value,
        baseline_cost=baseline.total_cost,
        relative_savings=savings_pct,
        optimal_solve_time=optimal.solve_time,
        optimal_gap=optimal.gap,
        optimal_status=optimal.status,
        baseline_strategy=baseline.strategy_name,
    )


def validate_solution(solution: RPMLSolution, instance) -> tuple[bool, list[str]]:
    """
    Validate that a solution satisfies all constraints.
    
    Args:
        solution: Solution to validate
        instance: Problem instance
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    n = instance.n
    T = instance.T
    
    # Check final balances are zero
    for j in range(n):
        final_balance = solution.balances[j, T-1]
        if abs(final_balance) > 1e-3:
            errors.append(f"Loan {j} final balance is {final_balance:.6f}, expected 0")
    
    # Check budget constraints
    for t in range(T):
        total_payments = np.sum(solution.payments[:, t])
        available = instance.monthly_income[t] + (solution.savings[t-1] if t > 0 else 0)
        used = total_payments + solution.savings[t]
        
        if used > available + 1e-3:
            errors.append(f"Month {t}: budget exceeded. Used {used:.2f}, available {available:.2f}")
    
    # Check balance dynamics (simplified check)
    for j in range(n):
        r_j = instance.release_time[j]
        if abs(solution.balances[j, r_j] - instance.principals[j]) > 1e-3:
            errors.append(f"Loan {j} initial balance mismatch at release time {r_j}")
    
    return len(errors) == 0, errors


def aggregate_results(results: list[ComparisonResult]) -> dict:
    """
    Aggregate comparison results across multiple instances.
    
    Args:
        results: List of ComparisonResult objects
    
    Returns:
        Dictionary with aggregated statistics
    """
    if not results:
        return {}
    
    # Group by number of loans
    by_n_loans = {}
    for r in results:
        if r.n_loans not in by_n_loans:
            by_n_loans[r.n_loans] = []
        by_n_loans[r.n_loans].append(r)
    
    aggregated = {
        'total_instances': len(results),
        'by_n_loans': {},
    }
    
    for n_loans, group_results in by_n_loans.items():
        savings = [r.relative_savings for r in group_results]
        solve_times = [r.optimal_solve_time for r in group_results]
        gaps = [r.optimal_gap for r in group_results]
        
        aggregated['by_n_loans'][n_loans] = {
            'count': len(group_results),
            'avg_savings_pct': np.mean(savings),
            'median_savings_pct': np.median(savings),
            'min_savings_pct': np.min(savings),
            'max_savings_pct': np.max(savings),
            'std_savings_pct': np.std(savings),
            'avg_solve_time': np.mean(solve_times),
            'median_solve_time': np.median(solve_times),
            'avg_gap': np.mean(gaps),
            'median_gap': np.median(gaps),
        }
    
    # Overall statistics
    all_savings = [r.relative_savings for r in results]
    aggregated['overall'] = {
        'avg_savings_pct': np.mean(all_savings),
        'median_savings_pct': np.median(all_savings),
        'min_savings_pct': np.min(all_savings),
        'max_savings_pct': np.max(all_savings),
    }
    
    return aggregated


def print_summary(results: list[ComparisonResult]):
    """
    Print a summary of comparison results.
    
    Args:
        results: List of ComparisonResult objects
    """
    if not results:
        print("No results to summarize.")
        return
    
    aggregated = aggregate_results(results)
    
    print("=" * 60)
    print("RPML EXPERIMENT RESULTS SUMMARY")
    print("=" * 60)
    print(f"\nTotal instances: {aggregated['total_instances']}")
    
    print("\nOverall Statistics:")
    overall = aggregated['overall']
    print(f"  Average savings: {overall['avg_savings_pct']:.2f}%")
    print(f"  Median savings: {overall['median_savings_pct']:.2f}%")
    print(f"  Min savings: {overall['min_savings_pct']:.2f}%")
    print(f"  Max savings: {overall['max_savings_pct']:.2f}%")
    
    print("\nBy Number of Loans:")
    for n_loans in sorted(aggregated['by_n_loans'].keys()):
        stats = aggregated['by_n_loans'][n_loans]
        print(f"\n  {n_loans} loans ({stats['count']} instances):")
        print(f"    Average savings: {stats['avg_savings_pct']:.2f}%")
        print(f"    Median savings: {stats['median_savings_pct']:.2f}%")
        print(f"    Range: [{stats['min_savings_pct']:.2f}%, {stats['max_savings_pct']:.2f}%]")
        print(f"    Average solve time: {stats['avg_solve_time']:.2f}s")
        print(f"    Average gap: {stats['avg_gap']:.2f}%")
    
    print("\n" + "=" * 60)

