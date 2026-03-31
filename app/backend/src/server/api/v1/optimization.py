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
    horizon_months: int = Field(..., ge=1, le=240)


class OptimizationRunResponse(BaseModel):
    status: str
    total_cost: float
    payments_matrix: list[list[float]]
    balances_matrix: list[list[float]]
    horizon_months: int
    baseline_comparison: dict
    input_mode: Literal["scenario_snapshot"] = MVP_INPUT_MODE
    assumptions: list[str] = Field(default_factory=lambda: list(MVP_ASSUMPTIONS))


class CreateOptimizationTaskRequest(BaseModel):
    horizon_months: int = Field(..., ge=1, le=240)


class CreateOptimizationTaskResponse(BaseModel):
    task_id: str
    status: Literal["pending"] = "pending"


class OptimizationTaskStatusResponse(BaseModel):
    status: Literal["pending", "completed", "failed"]
    task_id: str
    plan_id: str | None = None
    error: str | None = None


@router.post("/run", response_model=OptimizationRunResponse)
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
    )


@router.post(
    "/tasks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreateOptimizationTaskResponse,
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
    )
    return CreateOptimizationTaskResponse(task_id=out.task_id, status="pending")


@router.get(
    "/tasks/{task_id}",
    response_model=OptimizationTaskStatusResponse,
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
    )
