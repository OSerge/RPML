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
    """Results comparing optimal MILP solution with both baseline strategies."""
    instance_name: str
    n_loans: int
    optimal_cost: float
    optimal_solve_time: float
    optimal_gap: float
    optimal_status: str
    avalanche_cost: float
    avalanche_feasible: bool
    avalanche_savings: Optional[float]
    snowball_cost: float
    snowball_feasible: bool
    snowball_savings: Optional[float]


def relative_savings(optimal_cost: float, baseline_cost: float) -> Optional[float]:
    """
    Calculate relative savings percentage (MILP vs baseline).

    Formula: (baseline_cost - optimal_cost) / baseline_cost * 100
    Returns None if baseline_cost <= 0.
    """
    if baseline_cost <= 0:
        return None
    return (baseline_cost - optimal_cost) / baseline_cost * 100.0


def compare_solutions(
    optimal: RPMLSolution,
    avalanche: BaselineSolution,
    snowball: BaselineSolution,
    instance_name: str,
    n_loans: int,
    avalanche_feasible: bool,
    snowball_feasible: bool,
) -> ComparisonResult:
    """
    Compare MILP solution with both baseline strategies.

    When MILP status is not OPTIMAL/FEASIBLE, savings are set to None
    (comparison still records costs and status for checkpointing).
    """
    optimal_ok = optimal.status in ("OPTIMAL", "FEASIBLE")
    return ComparisonResult(
        instance_name=instance_name,
        n_loans=n_loans,
        optimal_cost=optimal.objective_value,
        optimal_solve_time=optimal.solve_time,
        optimal_gap=optimal.gap,
        optimal_status=optimal.status,
        avalanche_cost=avalanche.total_cost,
        avalanche_feasible=avalanche_feasible,
        avalanche_savings=relative_savings(optimal.objective_value, avalanche.total_cost) if (avalanche_feasible and optimal_ok) else None,
        snowball_cost=snowball.total_cost,
        snowball_feasible=snowball_feasible,
        snowball_savings=relative_savings(optimal.objective_value, snowball.total_cost) if (snowball_feasible and optimal_ok) else None,
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
    """
    if not results:
        return {}

    avalanche_savings = [r.avalanche_savings for r in results if r.avalanche_savings is not None]
    snowball_savings = [r.snowball_savings for r in results if r.snowball_savings is not None]

    by_n_loans = {}
    for r in results:
        if r.n_loans not in by_n_loans:
            by_n_loans[r.n_loans] = []
        by_n_loans[r.n_loans].append(r)

    aggregated = {
        'total_instances': len(results),
        'avalanche_feasible_count': sum(1 for r in results if r.avalanche_feasible),
        'avalanche_infeasible_count': sum(1 for r in results if not r.avalanche_feasible),
        'snowball_feasible_count': sum(1 for r in results if r.snowball_feasible),
        'snowball_infeasible_count': sum(1 for r in results if not r.snowball_feasible),
        'avalanche_savings': avalanche_savings,
        'snowball_savings': snowball_savings,
        'by_n_loans': {},
    }

    for n_loans, group in by_n_loans.items():
        av_s = [r.avalanche_savings for r in group if r.avalanche_savings is not None]
        sn_s = [r.snowball_savings for r in group if r.snowball_savings is not None]
        solve_times = [r.optimal_solve_time for r in group]
        gaps = [r.optimal_gap for r in group]
        aggregated['by_n_loans'][n_loans] = {
            'count': len(group),
            'avalanche_feasible': sum(1 for r in group if r.avalanche_feasible),
            'snowball_feasible': sum(1 for r in group if r.snowball_feasible),
            'avalanche_avg_savings': np.mean(av_s) if av_s else None,
            'snowball_avg_savings': np.mean(sn_s) if sn_s else None,
            'avg_solve_time': np.mean(solve_times),
            'avg_gap': np.mean(gaps),
        }

    aggregated['overall_avalanche'] = {
        'avg_savings_pct': float(np.mean(avalanche_savings)) if avalanche_savings else None,
        'median_savings_pct': float(np.median(avalanche_savings)) if avalanche_savings else None,
        'min_savings_pct': float(np.min(avalanche_savings)) if avalanche_savings else None,
        'max_savings_pct': float(np.max(avalanche_savings)) if avalanche_savings else None,
    }
    aggregated['overall_snowball'] = {
        'avg_savings_pct': float(np.mean(snowball_savings)) if snowball_savings else None,
        'median_savings_pct': float(np.median(snowball_savings)) if snowball_savings else None,
        'min_savings_pct': float(np.min(snowball_savings)) if snowball_savings else None,
        'max_savings_pct': float(np.max(snowball_savings)) if snowball_savings else None,
    }
    return aggregated


def print_summary(results: list[ComparisonResult]):
    """
    Print a summary of comparison results (MILP vs Avalanche and vs Snowball).
    """
    if not results:
        print("No results to summarize.")
        return

    agg = aggregate_results(results)

    print("=" * 60)
    print("RPML EXPERIMENT RESULTS SUMMARY")
    print("=" * 60)
    print(f"\nTotal instances: {agg['total_instances']}")
    print(f"\nDebt Avalanche: feasible {agg['avalanche_feasible_count']}, infeasible {agg['avalanche_infeasible_count']}")
    if agg['overall_avalanche']['avg_savings_pct'] is not None:
        o = agg['overall_avalanche']
        print(f"  MILP vs Avalanche (feasible only): avg savings {o['avg_savings_pct']:.2f}%, range [{o['min_savings_pct']:.2f}%, {o['max_savings_pct']:.2f}%]")
    else:
        print("  MILP vs Avalanche: no feasible instances")
    print(f"\nDebt Snowball: feasible {agg['snowball_feasible_count']}, infeasible {agg['snowball_infeasible_count']}")
    if agg['overall_snowball']['avg_savings_pct'] is not None:
        o = agg['overall_snowball']
        print(f"  MILP vs Snowball (feasible only): avg savings {o['avg_savings_pct']:.2f}%, range [{o['min_savings_pct']:.2f}%, {o['max_savings_pct']:.2f}%]")
    else:
        print("  MILP vs Snowball: no feasible instances")

    print("\nBy Number of Loans:")
    for n_loans in sorted(agg['by_n_loans'].keys()):
        s = agg['by_n_loans'][n_loans]
        print(f"\n  {n_loans} loans ({s['count']} instances): Avalanche feasible {s['avalanche_feasible']}, Snowball feasible {s['snowball_feasible']}")
        if s['avalanche_avg_savings'] is not None:
            print(f"    Avalanche avg savings: {s['avalanche_avg_savings']:.2f}%")
        if s['snowball_avg_savings'] is not None:
            print(f"    Snowball avg savings: {s['snowball_avg_savings']:.2f}%")
        print(f"    Avg solve time: {s['avg_solve_time']:.2f}s, avg gap: {s['avg_gap']:.2f}%")

    print("\n" + "=" * 60)

