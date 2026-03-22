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
    avalanche_valid: bool
    avalanche_feasible: bool
    avalanche_final_balance: float
    avalanche_horizon_spend_advantage: Optional[float]
    avalanche_savings: Optional[float]
    snowball_cost: float
    snowball_valid: bool
    snowball_feasible: bool
    snowball_final_balance: float
    snowball_horizon_spend_advantage: Optional[float]
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


def validate_baseline_solution(solution: BaselineSolution, instance) -> tuple[bool, list[str], float]:
    """
    Validate a baseline payment schedule independently of whether it fully repays
    all loans by the horizon.

    Returns:
        (is_valid, errors, max_abs_final_balance)
    """
    errors = []
    n = instance.n
    T = instance.T

    if solution.payments.shape != (n, T):
        errors.append(f"payments shape mismatch: {solution.payments.shape}")
    if solution.balances.shape != (n, T):
        errors.append(f"balances shape mismatch: {solution.balances.shape}")
    if solution.savings.shape != (T,):
        errors.append(f"savings shape mismatch: {solution.savings.shape}")

    if np.any(solution.payments < -1e-6):
        errors.append("negative payments detected")
    if np.any(solution.balances < -1e-6):
        errors.append("negative balances detected")
    if np.any(solution.savings < -1e-6):
        errors.append("negative savings detected")

    for j in range(n):
        r_j = int(instance.release_time[j])
        if np.any(np.abs(solution.payments[j, :r_j]) > 1e-6):
            errors.append(f"loan {j}: payments before release")
        if np.any(np.abs(solution.balances[j, :r_j]) > 1e-6):
            errors.append(f"loan {j}: balances before release")
        if r_j < T and abs(float(solution.payments[j, r_j])) > 1e-6:
            errors.append(f"loan {j}: payment in release month {r_j} must be zero (paper/MILP indexing)")

    for t in range(T):
        available = float(instance.monthly_income[t] + (solution.savings[t - 1] if t > 0 else 0.0))
        used = float(np.sum(solution.payments[:, t]) + solution.savings[t])
        if used > available + 1e-5:
            errors.append(f"month {t}: budget exceeded. Used {used:.6f}, available {available:.6f}")

    total_cost = float(np.sum(solution.payments))
    if abs(total_cost - float(solution.total_cost)) > 1e-5:
        errors.append("total_cost inconsistent with payments")

    max_abs_final_balance = float(np.max(np.abs(solution.balances[:, -1])))
    return len(errors) == 0, errors, max_abs_final_balance


def compare_solutions(
    optimal: RPMLSolution,
    avalanche: BaselineSolution,
    snowball: BaselineSolution,
    instance_name: str,
    n_loans: int,
    avalanche_valid: bool,
    avalanche_repaid_by_T: bool,
    avalanche_final_balance: float,
    snowball_valid: bool,
    snowball_repaid_by_T: bool,
    snowball_final_balance: float,
) -> ComparisonResult:
    """
    Compare MILP solution with both baseline strategies.

    When MILP status is not OPTIMAL/FEASIBLE, savings are set to None
    (comparison still records costs and status for checkpointing).
    """
    optimal_ok = optimal.status in ("OPTIMAL", "FEASIBLE")
    avalanche_horizon_spend_advantage = (
        relative_savings(optimal.objective_value, avalanche.total_cost)
        if (avalanche_valid and optimal_ok)
        else None
    )
    snowball_horizon_spend_advantage = (
        relative_savings(optimal.objective_value, snowball.total_cost)
        if (snowball_valid and optimal_ok)
        else None
    )
    return ComparisonResult(
        instance_name=instance_name,
        n_loans=n_loans,
        optimal_cost=optimal.objective_value,
        optimal_solve_time=optimal.solve_time,
        optimal_gap=optimal.gap,
        optimal_status=optimal.status,
        avalanche_cost=avalanche.total_cost,
        avalanche_valid=avalanche_valid,
        avalanche_feasible=avalanche_repaid_by_T,
        avalanche_final_balance=avalanche_final_balance,
        avalanche_horizon_spend_advantage=avalanche_horizon_spend_advantage,
        avalanche_savings=avalanche_horizon_spend_advantage if avalanche_repaid_by_T else None,
        snowball_cost=snowball.total_cost,
        snowball_valid=snowball_valid,
        snowball_feasible=snowball_repaid_by_T,
        snowball_final_balance=snowball_final_balance,
        snowball_horizon_spend_advantage=snowball_horizon_spend_advantage,
        snowball_savings=snowball_horizon_spend_advantage if snowball_repaid_by_T else None,
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

    def _metric_stats(values: list[float]) -> dict | None:
        if not values:
            return None
        arr = np.array(values, dtype=float)
        return {
            "count": int(len(arr)),
            "avg": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
        }

    def _status_counts(group: list[ComparisonResult]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in group:
            counts[result.optimal_status] = counts.get(result.optimal_status, 0) + 1
        return counts

    def _status_instances(group: list[ComparisonResult]) -> dict[str, list[str]]:
        instances: dict[str, list[str]] = {}
        for result in group:
            instances.setdefault(result.optimal_status, []).append(result.instance_name)
        for names in instances.values():
            names.sort()
        return instances

    def _solve_stats(group: list[ComparisonResult]) -> dict:
        solve_times = np.array([r.optimal_solve_time for r in group], dtype=float)
        gaps = np.array([r.optimal_gap for r in group], dtype=float)
        return {
            "avg_solve_time": float(np.mean(solve_times)),
            "median_solve_time": float(np.median(solve_times)),
            "p90_solve_time": float(np.percentile(solve_times, 90)),
            "max_solve_time": float(np.max(solve_times)),
            "avg_gap": float(np.mean(gaps)),
            "median_gap": float(np.median(gaps)),
            "max_gap": float(np.max(gaps)),
        }

    def _problem_instances(group: list[ComparisonResult], status: str) -> list[dict]:
        problem_results = [r for r in group if r.optimal_status == status]
        problem_results.sort(key=lambda r: (-r.optimal_solve_time, r.instance_name))
        return [
            {
                "instance_name": r.instance_name,
                "solve_time": r.optimal_solve_time,
                "gap": r.optimal_gap,
            }
            for r in problem_results
        ]

    def _slowest_instances(group: list[ComparisonResult], limit: int = 3) -> list[dict]:
        slowest = sorted(group, key=lambda r: (-r.optimal_solve_time, r.instance_name))[:limit]
        return [
            {
                "instance_name": r.instance_name,
                "status": r.optimal_status,
                "solve_time": r.optimal_solve_time,
                "gap": r.optimal_gap,
            }
            for r in slowest
        ]

    def _baseline_stats(group: list[ComparisonResult], baseline_name: str) -> dict:
        horizon_attr = f"{baseline_name}_horizon_spend_advantage"
        savings_attr = f"{baseline_name}_savings"
        valid_attr = f"{baseline_name}_valid"
        feasible_attr = f"{baseline_name}_feasible"

        all_horizon = [
            getattr(r, horizon_attr)
            for r in group
            if getattr(r, horizon_attr) is not None
        ]
        optimal_horizon = [
            getattr(r, horizon_attr)
            for r in group
            if r.optimal_status == "OPTIMAL" and getattr(r, horizon_attr) is not None
        ]
        feasible_horizon = [
            getattr(r, horizon_attr)
            for r in group
            if r.optimal_status == "FEASIBLE" and getattr(r, horizon_attr) is not None
        ]
        repaid_savings = [
            getattr(r, savings_attr)
            for r in group
            if getattr(r, savings_attr) is not None
        ]

        return {
            "valid_count": sum(1 for r in group if getattr(r, valid_attr)),
            "feasible_count": sum(1 for r in group if getattr(r, feasible_attr)),
            "infeasible_count": sum(1 for r in group if not getattr(r, feasible_attr)),
            "all_horizon": _metric_stats(all_horizon),
            "optimal_only_horizon": _metric_stats(optimal_horizon),
            "feasible_only_horizon": _metric_stats(feasible_horizon),
            "repaid_only_savings": _metric_stats(repaid_savings),
        }

    by_n_loans = {}
    for r in results:
        if r.n_loans not in by_n_loans:
            by_n_loans[r.n_loans] = []
        by_n_loans[r.n_loans].append(r)

    aggregated = {
        "total_instances": len(results),
        "status_counts": _status_counts(results),
        "status_instances": _status_instances(results),
        "optimal_count": sum(1 for r in results if r.optimal_status == "OPTIMAL"),
        "usable_count": sum(1 for r in results if r.optimal_status in ("OPTIMAL", "FEASIBLE")),
        "solve_stats": _solve_stats(results),
        "feasible_instances": _problem_instances(results, "FEASIBLE"),
        "not_solved_instances": _problem_instances(results, "NOT_SOLVED"),
        "slowest_instances": _slowest_instances(results),
        "avalanche": _baseline_stats(results, "avalanche"),
        "snowball": _baseline_stats(results, "snowball"),
        "by_n_loans": {},
    }

    for n_loans, group in by_n_loans.items():
        aggregated["by_n_loans"][n_loans] = {
            "count": len(group),
            "status_counts": _status_counts(group),
            "status_instances": _status_instances(group),
            "optimal_count": sum(1 for r in group if r.optimal_status == "OPTIMAL"),
            "usable_count": sum(1 for r in group if r.optimal_status in ("OPTIMAL", "FEASIBLE")),
            "solve_stats": _solve_stats(group),
            "feasible_instances": _problem_instances(group, "FEASIBLE"),
            "not_solved_instances": _problem_instances(group, "NOT_SOLVED"),
            "slowest_instances": _slowest_instances(group),
            "avalanche": _baseline_stats(group, "avalanche"),
            "snowball": _baseline_stats(group, "snowball"),
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

    def _format_stats(label: str, stats: dict | None) -> str:
        if stats is None:
            return f"{label}: no instances"
        return (
            f"{label}: avg {stats['avg']:.2f}%, median {stats['median']:.2f}%, "
            f"range [{stats['min']:.2f}%, {stats['max']:.2f}%], n={stats['count']}"
        )

    def _format_status_counts(status_counts: dict[str, int]) -> str:
        ordered = ["OPTIMAL", "FEASIBLE", "NOT_SOLVED", "INFEASIBLE", "ABNORMAL", "UNBOUNDED"]
        parts = [f"{status} {status_counts[status]}" for status in ordered if status in status_counts]
        remaining = sorted(k for k in status_counts.keys() if k not in ordered)
        parts.extend(f"{status} {status_counts[status]}" for status in remaining)
        return ", ".join(parts) if parts else "none"

    def _print_baseline_block(title: str, baseline: dict) -> None:
        print(
            f"\n{title}: valid {baseline['valid_count']}, "
            f"repaid_by_T {baseline['feasible_count']}, "
            f"not_repaid_by_T {baseline['infeasible_count']}"
        )
        print("  " + _format_stats("All comparable (OPTIMAL+FEASIBLE)", baseline["all_horizon"]))
        print("  " + _format_stats("OPTIMAL-only horizon advantage", baseline["optimal_only_horizon"]))
        if baseline["feasible_only_horizon"] is not None:
            print("  " + _format_stats("FEASIBLE-only horizon advantage", baseline["feasible_only_horizon"]))
        print("  " + _format_stats("Repaid-by-T savings", baseline["repaid_only_savings"]))

    def _format_rate(count: int, total: int) -> str:
        if total == 0:
            return "0/0 (0.0%)"
        return f"{count}/{total} ({100.0 * count / total:.1f}%)"

    def _format_solve_stats(solve_stats: dict) -> str:
        return (
            f"avg {solve_stats['avg_solve_time']:.2f}s, "
            f"median {solve_stats['median_solve_time']:.2f}s, "
            f"p90 {solve_stats['p90_solve_time']:.2f}s, "
            f"max {solve_stats['max_solve_time']:.2f}s"
        )

    def _format_gap_stats(solve_stats: dict) -> str:
        return (
            f"avg {solve_stats['avg_gap']:.2f}%, "
            f"median {solve_stats['median_gap']:.2f}%, "
            f"max {solve_stats['max_gap']:.2f}%"
        )

    def _format_problem_list(items: list[dict], limit: int = 8) -> str:
        if not items:
            return "none"
        shown = items[:limit]
        rendered = ", ".join(
            f"{item['instance_name']} ({item['solve_time']:.2f}s, gap {item['gap']:.2f}%)"
            for item in shown
        )
        if len(items) > limit:
            rendered += f", ... +{len(items) - limit} more"
        return rendered

    def _format_slowest_list(items: list[dict]) -> str:
        if not items:
            return "none"
        return ", ".join(
            f"{item['instance_name']} [{item['status']}, {item['solve_time']:.2f}s, gap {item['gap']:.2f}%]"
            for item in items
        )

    print("=" * 60)
    print("RPML EXPERIMENT RESULTS SUMMARY")
    print("=" * 60)
    print(f"\nTotal instances: {agg['total_instances']}")
    print(f"MILP statuses: {_format_status_counts(agg['status_counts'])}")
    print("\nHeadline:")
    print(f"  OPTIMAL coverage: {_format_rate(agg['optimal_count'], agg['total_instances'])}")
    print(f"  Usable coverage (OPTIMAL+FEASIBLE): {_format_rate(agg['usable_count'], agg['total_instances'])}")
    print("  Solve time: " + _format_solve_stats(agg["solve_stats"]))
    print("  Solver gap: " + _format_gap_stats(agg["solve_stats"]))
    print("  Headline advantage vs Avalanche: " + _format_stats("OPTIMAL-only", agg["avalanche"]["optimal_only_horizon"]).replace("OPTIMAL-only: ", ""))
    print("  Headline advantage vs Snowball: " + _format_stats("OPTIMAL-only", agg["snowball"]["optimal_only_horizon"]).replace("OPTIMAL-only: ", ""))

    _print_baseline_block("Debt Avalanche", agg["avalanche"])
    _print_baseline_block("Debt Snowball", agg["snowball"])

    print("\nBy Number of Loans:")
    for n_loans in sorted(agg["by_n_loans"].keys()):
        s = agg["by_n_loans"][n_loans]
        print(f"\n  {n_loans} loans")
        print(f"    Instances: {s['count']}")
        print(f"    MILP statuses: {_format_status_counts(s['status_counts'])}")
        print(f"    OPTIMAL coverage: {_format_rate(s['optimal_count'], s['count'])}")
        print(f"    Usable coverage: {_format_rate(s['usable_count'], s['count'])}")
        print(
            f"    Avalanche: valid {s['avalanche']['valid_count']}, "
            f"repaid_by_T {s['avalanche']['feasible_count']}, "
            f"not_repaid_by_T {s['avalanche']['infeasible_count']}"
        )
        print(
            f"    Snowball: valid {s['snowball']['valid_count']}, "
            f"repaid_by_T {s['snowball']['feasible_count']}, "
            f"not_repaid_by_T {s['snowball']['infeasible_count']}"
        )
        print("    " + _format_stats("Avalanche OPTIMAL-only", s["avalanche"]["optimal_only_horizon"]))
        print("    " + _format_stats("Snowball OPTIMAL-only", s["snowball"]["optimal_only_horizon"]))
        print("    " + _format_stats("Avalanche OPTIMAL+FEASIBLE", s["avalanche"]["all_horizon"]))
        print("    " + _format_stats("Snowball OPTIMAL+FEASIBLE", s["snowball"]["all_horizon"]))
        print("    Solve time: " + _format_solve_stats(s["solve_stats"]))
        print("    Solver gap: " + _format_gap_stats(s["solve_stats"]))
        print("    Slowest instances: " + _format_slowest_list(s["slowest_instances"]))

    print("\nProblem cases:")
    print("  FEASIBLE instances: " + _format_problem_list(agg["feasible_instances"]))
    print("  NOT_SOLVED instances: " + _format_problem_list(agg["not_solved_instances"]))

    print("\n" + "=" * 60)

