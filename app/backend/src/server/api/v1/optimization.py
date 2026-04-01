from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server.api.deps import get_current_user
from server.application.use_cases.run_optimization_async import (
    execute_create_async_optimization_task,
    execute_get_optimization_task_status,
)
from server.application.use_cases.run_optimization_sync import (
    MVP_ASSUMPTIONS,
    MVP_INPUT_MODE,
    OptimizationSolverFailed,
    execute_run_optimization_sync,
)
from server.infrastructure.rpml_adapter.instance_builder import OptimizationInstanceError
from server.domain.models.user import UserRead
from server.infrastructure.db.session import get_db

router = APIRouter()


class OptimizationRunRequest(BaseModel):
    horizon_months: int = Field(
        ...,
        ge=1,
        le=240,
        description="Горизонт планирования в месяцах.",
    )
    ru_mode: bool = Field(
        default=True,
        description="Если true, применяются правила RU-режима по досрочному погашению.",
    )
    mc_income: bool = Field(
        default=False,
        description="Если true, дополнительно рассчитывается Monte Carlo summary по траекториям дохода.",
    )


class OptimizationRunResponse(BaseModel):
    status: str = Field(description="Статус решения MILP (например, OPTIMAL/FEASIBLE).")
    total_cost: float = Field(description="Стоимость базового детерминированного плана.")
    payments_matrix: list[list[float]] = Field(description="Матрица платежей [loan][month].")
    balances_matrix: list[list[float]] = Field(description="Матрица остатков [loan][month].")
    horizon_months: int = Field(description="Использованный горизонт планирования.")
    baseline_comparison: dict = Field(
        description="Сравнение MILP-плана с baseline-стратегиями (avalanche/snowball)."
    )
    input_mode: Literal["scenario_snapshot"] = MVP_INPUT_MODE
    assumptions: list[str] = Field(
        default_factory=lambda: list(MVP_ASSUMPTIONS),
        description="Список допущений, использованных при расчете.",
    )
    ru_mode: bool = Field(description="Фактически использованный RU-режим.")
    mc_income: bool = Field(description="Флаг Monte Carlo режима для этого расчета.")
    mc_summary: dict | None = Field(
        default=None,
        description=(
            "Агрегаты Monte Carlo по стоимости и времени решения "
            "(mean/median/p90, доля infeasible и т.д.)."
        ),
    )


class CreateOptimizationTaskRequest(BaseModel):
    horizon_months: int = Field(
        ...,
        ge=1,
        le=240,
        description="Горизонт планирования в месяцах.",
    )
    ru_mode: bool = Field(
        default=True,
        description="Если true, применяются правила RU-режима.",
    )
    mc_income: bool = Field(
        default=False,
        description="Если true, в фоне будет рассчитан Monte Carlo summary.",
    )


class CreateOptimizationTaskResponse(BaseModel):
    task_id: str = Field(description="Идентификатор асинхронной задачи.")
    status: Literal["pending"] = "pending"
    ru_mode: bool = Field(description="RU-режим, зафиксированный в задаче.")
    mc_income: bool = Field(description="MC-режим, зафиксированный в задаче.")


class OptimizationTaskStatusResponse(BaseModel):
    status: Literal["pending", "completed", "failed"]
    task_id: str = Field(description="Идентификатор асинхронной задачи.")
    plan_id: str | None = Field(
        default=None,
        description="Идентификатор готового плана (заполняется при completed).",
    )
    error: str | None = Field(
        default=None,
        description="Текст ошибки (заполняется при failed).",
    )
    ru_mode: bool = Field(description="RU-режим задачи.")
    mc_income: bool = Field(description="MC-режим задачи.")


@router.post(
    "/run",
    response_model=OptimizationRunResponse,
    summary="Синхронный запуск оптимизации",
    description=(
        "Выполняет оптимизацию в рамках одного HTTP-запроса. "
        "Возвращает базовый план и, при `mc_income=true`, дополнительный Monte Carlo summary."
    ),
    responses={
        400: {"$ref": "#/components/responses/ErrorContent"},
        401: {"description": "Пользователь не аутентифицирован."},
        422: {"$ref": "#/components/responses/ErrorContent"},
    },
)
def run_optimization_sync(
    body: OptimizationRunRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> OptimizationRunResponse:
    try:
        result = execute_run_optimization_sync(
            db,
            current_user.id,
            body.horizon_months,
            ru_mode=body.ru_mode,
            mc_income=body.mc_income,
        )
    except OptimizationInstanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None
    except OptimizationSolverFailed as exc:
        hint = (
            " If status is INFEASIBLE, the horizon may be too short for this scenario "
            "(MILP requires zero balances at the last month; try horizon_months equal to the scenario profile)."
        )
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Optimization did not return a usable plan." + hint,
                "solver_status": exc.solver_status,
            },
        ) from None
    return OptimizationRunResponse(
        status=result.solver_status,
        total_cost=result.total_cost,
        payments_matrix=result.payments_matrix,
        balances_matrix=result.balances_matrix,
        horizon_months=result.horizon_months,
        baseline_comparison=result.baseline_comparison,
        ru_mode=result.ru_mode,
        mc_income=result.mc_income,
        mc_summary=result.mc_summary,
    )


@router.post(
    "/tasks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreateOptimizationTaskResponse,
    summary="Создать асинхронную задачу оптимизации",
    description="Ставит расчет в очередь Celery и сразу возвращает task_id.",
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
        422: {"$ref": "#/components/responses/ErrorContent"},
    },
)
def create_optimization_task(
    body: CreateOptimizationTaskRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> CreateOptimizationTaskResponse:
    out = execute_create_async_optimization_task(
        db,
        current_user.id,
        body.horizon_months,
        ru_mode=body.ru_mode,
        mc_income=body.mc_income,
    )
    return CreateOptimizationTaskResponse(
        task_id=out.task_id,
        status="pending",
        ru_mode=out.ru_mode,
        mc_income=out.mc_income,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=OptimizationTaskStatusResponse,
    summary="Статус асинхронной задачи оптимизации",
    description=(
        "Возвращает текущий статус задачи. "
        "При completed в ответе присутствует `plan_id`, который можно запросить через `/optimization/plans/{plan_id}`."
    ),
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
        404: {"$ref": "#/components/responses/ErrorContent"},
        422: {"$ref": "#/components/responses/ErrorContent"},
    },
)
def get_optimization_task_status(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> OptimizationTaskStatusResponse:
    row = execute_get_optimization_task_status(db, current_user.id, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return OptimizationTaskStatusResponse(
        status=row.status,
        task_id=row.task_id,
        plan_id=row.plan_id,
        error=row.error,
        ru_mode=row.ru_mode,
        mc_income=row.mc_income,
    )
