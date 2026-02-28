"""AI explanation chat endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_current_user
from app.core.database import get_db
from app.models.debt import Debt
from app.models.optimization_plan import OptimizationPlan
from app.models.user import User
from app.services.explanation import ExplanationService
from app.services.llm_context import build_llm_context

router = APIRouter()


class ExplainRequest(BaseModel):
    question: str
    plan_context: str | None = None
    include_user_data: bool = True


@router.post("")
async def explain(
    data: ExplainRequest,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream AI explanation with user debt and plan context."""
    context = data.plan_context

    if data.include_user_data:
        debts_result = await db.execute(
            select(Debt).where(Debt.user_id == current_user.id)
        )
        debts = list(debts_result.scalars().all())

        plan_result = await db.execute(
            select(OptimizationPlan)
            .where(OptimizationPlan.user_id == current_user.id)
            .order_by(OptimizationPlan.created_at.desc())
            .limit(1)
        )
        latest_plan = plan_result.scalar_one_or_none()

        plan_data = None
        if latest_plan:
            plan_data = {
                "payments_matrix": latest_plan.payments_matrix,
                "total_cost": float(latest_plan.total_cost),
                "savings_vs_minimum": float(latest_plan.savings_vs_minimum) if latest_plan.savings_vs_minimum else None,
            }

        auto_context = build_llm_context(debts, plan_data)

        if context:
            context = f"{auto_context}\n\n{context}"
        else:
            context = auto_context

    service = ExplanationService()

    async def generate():
        async for chunk in service.explain_stream(data.question, context):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
    )
