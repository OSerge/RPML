"""MILP optimization task."""

import uuid

from rpml import solve_rpml

from app.celery_app import celery_app
from app.core.database_sync import SyncSession
from app.models.optimization_plan import OptimizationPlan
from app.services.instance_builder import OptimizationParams, build_instance, compute_baseline_cost


@celery_app.task(bind=True)
def run_optimization(self, data: dict) -> dict:
    """
    Run RPML optimization in Celery worker.
    
    Args:
        data: Dict with keys:
            - user_id: UUID string
            - debts: List of debt payloads (dict)
            - monthly_budget: float
            - budget_by_month: Optional[list[float]]
            - horizon_months: int
            
    Returns:
        Dict with plan_id or error
    """
    try:
        user_id = uuid.UUID(data["user_id"])
        debts = data["debts"]
        
        params = OptimizationParams(
            horizon_months=data.get("horizon_months", 24),
            monthly_budget=data.get("monthly_budget", 50000.0),
            budget_by_month=data.get("budget_by_month"),
            time_limit_seconds=60,
        )
        
        instance = build_instance(debts, params)
        solution = solve_rpml(instance, time_limit_seconds=params.time_limit_seconds)
        
        total_cost = solution.objective_value
        status_val = solution.status
        
        if (
            total_cost is None
            or total_cost != total_cost
            or total_cost == float("inf")
            or status_val not in ("OPTIMAL", "FEASIBLE")
        ):
            return {
                "status": "failed",
                "error": f"Оптимизация не нашла допустимый план (статус: {status_val})",
            }
        
        debt_names = [d["name"] for d in debts]
        payments_matrix = {
            name: solution.payments[j, :].tolist() for j, name in enumerate(debt_names)
        }
        
        baseline_cost = compute_baseline_cost(debts, params.horizon_months)
        savings = baseline_cost - total_cost if total_cost < float("inf") else None
        
        with SyncSession() as db:
            plan = OptimizationPlan(
                user_id=user_id,
                payments_matrix=payments_matrix,
                total_cost=float(total_cost),
                savings_vs_minimum=savings,
            )
            db.add(plan)
            db.commit()
            db.refresh(plan)
            
            plan_id = str(plan.id)
        
        return {
            "status": "completed",
            "plan_id": plan_id,
            "total_cost": float(total_cost),
            "savings_vs_minimum": savings,
            "solve_time": solution.solve_time,
        }
        
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
        }
