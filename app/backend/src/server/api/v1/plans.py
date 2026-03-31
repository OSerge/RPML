from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server.api.deps import get_current_user
from server.application.use_cases.get_plan import execute_get_plan
from server.application.use_cases.run_optimization_sync import (
    MVP_ASSUMPTIONS,
    MVP_INPUT_MODE,
)
from server.domain.models.user import UserRead
from server.infrastructure.db.session import get_db

router = APIRouter()


class OptimizationPlanResponse(BaseModel):
    status: str
    total_cost: float
    payments_matrix: list[list[float]]
    input_mode: str = MVP_INPUT_MODE
    assumptions: list[str] = Field(default_factory=lambda: list(MVP_ASSUMPTIONS))


@router.get(
    "/plans/{plan_id}",
    response_model=OptimizationPlanResponse,
)
def get_optimization_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> OptimizationPlanResponse:
    result = execute_get_plan(db, current_user.id, plan_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return OptimizationPlanResponse(
        status=result.status,
        total_cost=result.total_cost,
        payments_matrix=result.payments_matrix,
        input_mode=result.input_mode,
        assumptions=result.assumptions,
    )
