"""Optimization plans endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_current_user
from app.core.database import get_db
from app.models.debt import Debt
from app.models.optimization_plan import OptimizationPlan
from app.models.user import User

router = APIRouter()


@router.post("/async")
async def run_optimization_async(
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
    from app.tasks.optimize import run_optimization

    data = {
        "debts": [
            {
                "name": d.name,
                "current_balance": float(d.current_balance),
                "interest_rate_annual": float(d.interest_rate_annual),
                "min_payment_pct": float(d.min_payment_pct),
            }
            for d in debts
        ],
        "horizon_months": 24,
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
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Debt).where(Debt.user_id == current_user.id))
    debts = result.scalars().all()
    if not debts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No debts to optimize",
        )
    from app.services.rpml_optimizer import RPMLOptimizerService

    service = RPMLOptimizerService()
    plan_data = await service.optimize(debts)
    plan = OptimizationPlan(
        user_id=current_user.id,
        payments_matrix=plan_data["payments_matrix"],
        total_cost=plan_data["total_cost"],
        savings_vs_minimum=plan_data.get("savings_vs_minimum"),
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return {
        "id": str(plan.id),
        "total_cost": float(plan.total_cost),
        "payments_matrix": plan_data["payments_matrix"],
        "savings_vs_minimum": plan_data.get("savings_vs_minimum"),
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
