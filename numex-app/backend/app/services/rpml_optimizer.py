"""RPML optimizer service - wrapper over MILP model."""

from typing import Optional

from rpml import solve_rpml

from app.models.debt import Debt
from app.services.instance_builder import OptimizationParams, build_instance, compute_baseline_cost


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

        instance = build_instance(debts, params)
        solution = solve_rpml(instance, time_limit_seconds=params.time_limit_seconds)

        debt_names = [d.name for d in debts]
        payments_matrix = {}
        balances_matrix = {}
        for j, name in enumerate(debt_names):
            payments_matrix[name] = solution.payments[j, :].tolist()
            balances_matrix[name] = solution.balances[j, :].tolist()

        baseline_cost = compute_baseline_cost(debts, horizon_months)
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
