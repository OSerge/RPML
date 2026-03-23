"""Optimization plans endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_current_user
from app.core.database import get_db
from app.models.debt import Debt
from app.models.optimization_plan import OptimizationPlan
from app.models.user import User

router = APIRouter()


class OptimizationRequest(BaseModel):
    """Request body for optimization."""
    monthly_budget: float = 50000.0
    budget_by_month: list[float] | None = None
    horizon_months: int = 24


def _debt_to_payload(d: Debt) -> dict:
    """Serialize Debt model to dict payload for Celery."""
    return {
        "id": str(d.id),
        "name": d.name,
        "debt_type": d.debt_type.value,
        "current_balance": float(d.current_balance),
        "interest_rate_annual": float(d.interest_rate_annual),
        "payment_type": d.payment_type.value,
        "min_payment_pct": float(d.min_payment_pct),
        "fixed_payment": float(d.fixed_payment) if d.fixed_payment else None,
        "prepayment_policy": d.prepayment_policy.value,
        "prepayment_penalty_pct": float(d.prepayment_penalty_pct) if d.prepayment_penalty_pct else None,
        "late_fee_rate": float(d.late_fee_rate or 0),
        "term_months": d.term_months,
        "start_date": d.start_date.isoformat(),
    }


@router.post("/async")
async def run_optimization_async(
    request: OptimizationRequest | None = None,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start async optimization via Celery, returns task_id for polling."""
    result = await db.execute(select(Debt).where(Debt.user_id == current_user.id))
    debts = result.scalars().all()
    if not debts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No debts to optimize",
        )
    
    params = request or OptimizationRequest()
    
    from app.tasks.optimize import run_optimization

    data = {
        "user_id": str(current_user.id),
        "debts": [_debt_to_payload(d) for d in debts],
        "monthly_budget": params.monthly_budget,
        "budget_by_month": params.budget_by_month,
        "horizon_months": params.horizon_months,
    }
    task = run_optimization.delay(data)
    return {"task_id": task.id}


@router.get("/async/{task_id}")
async def get_optimization_result(
    task_id: str,
    current_user: User = Depends(require_current_user),
):
    """Poll for async optimization result."""
    from app.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    if result.ready():
        if result.successful():
            return {"status": "completed", "result": result.get()}
        return {"status": "failed", "error": str(result.result)}
    return {"status": "pending"}


@router.post("")
async def run_optimization(
    request: OptimizationRequest | None = None,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run synchronous optimization on user debts."""
    result = await db.execute(select(Debt).where(Debt.user_id == current_user.id))
    debts = result.scalars().all()
    if not debts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No debts to optimize",
        )

    params = request or OptimizationRequest()

    from app.services.rpml_optimizer import RPMLOptimizerService

    service = RPMLOptimizerService()
    plan_data = await service.optimize(
        debts=list(debts),
        monthly_budget=params.monthly_budget,
        budget_by_month=params.budget_by_month,
        horizon_months=params.horizon_months,
    )

    total_cost = plan_data["total_cost"]
    status_val = plan_data.get("status", "")
    if (
        total_cost is None
        or total_cost != total_cost
        or total_cost == float("inf")
        or status_val not in ("OPTIMAL", "FEASIBLE")
    ):
        msg = "Оптимизация не нашла допустимый план. Увеличьте бюджет или проверьте параметры долгов."
        if status_val:
            msg += f" (статус: {status_val})"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=msg,
        )

    plan = OptimizationPlan(
        user_id=current_user.id,
        payments_matrix=plan_data["payments_matrix"],
        total_cost=float(total_cost),
        savings_vs_minimum=plan_data.get("savings_vs_minimum"),
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    return {
        "id": str(plan.id),
        "total_cost": float(plan.total_cost),
        "payments_matrix": plan_data["payments_matrix"],
        "balances_matrix": plan_data.get("balances_matrix"),
        "savings_vs_minimum": plan_data.get("savings_vs_minimum"),
        "baseline_cost": plan_data.get("baseline_cost"),
        "status": plan_data.get("status"),
        "solve_time": plan_data.get("solve_time"),
        "horizon_months": plan_data.get("horizon_months"),
    }


@router.get("/{plan_id}")
async def get_plan(
    plan_id: UUID,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OptimizationPlan).where(
            OptimizationPlan.id == plan_id,
            OptimizationPlan.user_id == current_user.id,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return {
        "id": str(plan.id),
        "payments_matrix": plan.payments_matrix,
        "total_cost": float(plan.total_cost),
        "savings_vs_minimum": float(plan.savings_vs_minimum) if plan.savings_vs_minimum else None,
        "created_at": plan.created_at.isoformat(),
    }
