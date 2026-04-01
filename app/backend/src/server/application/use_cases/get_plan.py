"""Retrieve a persisted optimization plan by id."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from server.application.use_cases.run_optimization_sync import MVP_INPUT_MODE
from server.infrastructure.db.models.optimization_plan import OptimizationPlanORM


@dataclass(frozen=True)
class PlanResult:
    status: str
    total_cost: float
    payments_matrix: list[list[float]]
    input_mode: str
    assumptions: list[str]
    ru_mode: bool
    mc_income: bool
    mc_summary: dict | None


def execute_get_plan(db: Session, user_id: int, plan_id: str) -> PlanResult | None:
    row = db.get(OptimizationPlanORM, plan_id)
    if row is None or row.user_id != user_id:
        return None
    assumptions = row.assumptions if isinstance(row.assumptions, list) else list(row.assumptions)
    return PlanResult(
        status=row.solver_status,
        total_cost=float(row.total_cost),
        payments_matrix=row.payments_matrix,
        input_mode=row.input_mode or MVP_INPUT_MODE,
        assumptions=[str(x) for x in assumptions],
        ru_mode=bool(row.ru_mode),
        mc_income=bool(row.mc_income),
        mc_summary=row.mc_summary if isinstance(row.mc_summary, dict) else None,
    )
