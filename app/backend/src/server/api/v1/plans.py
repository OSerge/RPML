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
    status: str = Field(description="Статус решения (OPTIMAL/FEASIBLE/...).")
    total_cost: float = Field(description="Стоимость базового детерминированного плана.")
    payments_matrix: list[list[float]] = Field(description="Матрица платежей [loan][month].")
    input_mode: str = MVP_INPUT_MODE
    assumptions: list[str] = Field(
        default_factory=lambda: list(MVP_ASSUMPTIONS),
        description="Список допущений, использованных при расчете.",
    )
    ru_mode: bool = Field(description="Фактически использованный RU-режим.")
    mc_income: bool = Field(description="Флаг MC-режима для данного плана.")
    mc_summary: dict | None = Field(
        default=None,
        description="Агрегаты Monte Carlo, если расчет выполнялся с `mc_income=true`.",
    )


@router.get(
    "/plans/{plan_id}",
    response_model=OptimizationPlanResponse,
    summary="Получить асинхронный план по ID",
    description="Возвращает результат расчета, ранее завершенного через `/optimization/tasks`.",
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
        404: {"$ref": "#/components/responses/ErrorContent"},
        422: {"$ref": "#/components/responses/ErrorContent"},
    },
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
        ru_mode=result.ru_mode,
        mc_income=result.mc_income,
        mc_summary=result.mc_summary,
    )
