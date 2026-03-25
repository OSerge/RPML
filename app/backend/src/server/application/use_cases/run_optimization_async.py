"""Enqueue and process async optimization jobs (Celery worker)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from server.application.use_cases.run_optimization_sync import (
    MVP_ASSUMPTIONS,
    MVP_INPUT_MODE,
    OptimizationSolverFailed,
    execute_run_optimization_sync,
)
from server.infrastructure.rpml_adapter.instance_builder import OptimizationInstanceError
from server.infrastructure.db.models.optimization_plan import OptimizationPlanORM
from server.infrastructure.db.models.optimization_task import OptimizationTaskORM


@dataclass(frozen=True)
class CreateAsyncTaskResult:
    task_id: str
    status: str = "pending"


def execute_create_async_optimization_task(
    db: Session,
    user_id: int,
    horizon_months: int,
) -> CreateAsyncTaskResult:
    task_id = str(uuid.uuid4())
    row = OptimizationTaskORM(
        celery_task_id=task_id,
        user_id=user_id,
        status="pending",
        horizon_months=horizon_months,
        plan_id=None,
        error_message=None,
    )
    db.add(row)
    db.commit()
    from server.infrastructure.queue.tasks import run_optimization_task

    run_optimization_task.apply_async(args=(), task_id=task_id)
    return CreateAsyncTaskResult(task_id=task_id)


@dataclass(frozen=True)
class TaskStatusResult:
    status: str
    task_id: str
    plan_id: str | None
    error: str | None


def execute_get_optimization_task_status(
    db: Session,
    user_id: int,
    task_id: str,
) -> TaskStatusResult | None:
    row = db.get(OptimizationTaskORM, task_id)
    if row is None or row.user_id != user_id:
        return None
    err = row.error_message
    return TaskStatusResult(
        status=row.status,
        task_id=row.celery_task_id,
        plan_id=row.plan_id,
        error=err,
    )


def _persist_completed_plan(
    db: Session,
    *,
    user_id: int,
    task_id: str,
    total_cost: float,
    payments_matrix: list[list[float]],
    solver_status: str,
) -> None:
    plan_id = str(uuid.uuid4())
    plan = OptimizationPlanORM(
        id=plan_id,
        user_id=user_id,
        total_cost=total_cost,
        payments_matrix=payments_matrix,
        solver_status=solver_status,
        input_mode=MVP_INPUT_MODE,
        assumptions=list(MVP_ASSUMPTIONS),
    )
    db.add(plan)
    task = db.get(OptimizationTaskORM, task_id)
    if task is None:
        db.rollback()
        return
    task.status = "completed"
    task.plan_id = plan_id
    task.error_message = None
    db.commit()


def _persist_failed(db: Session, *, task_id: str, message: str) -> None:
    task = db.get(OptimizationTaskORM, task_id)
    if task is None:
        db.rollback()
        return
    task.status = "failed"
    task.plan_id = None
    task.error_message = message
    db.commit()


def run_optimization_job_for_task_id(task_id: str) -> None:
    """Worker entry: load task row, run sync optimization, update status."""
    from server.infrastructure.db.session import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(OptimizationTaskORM, task_id)
        if task is None:
            return
        user_id = task.user_id
        horizon = task.horizon_months
        try:
            result = execute_run_optimization_sync(db, user_id, horizon, mode="async")
        except OptimizationInstanceError as exc:
            _persist_failed(db, task_id=task_id, message=str(exc))
            return
        except OptimizationSolverFailed as exc:
            _persist_failed(
                db,
                task_id=task_id,
                message=f"Solver status: {exc.solver_status}",
            )
            return
        _persist_completed_plan(
            db,
            user_id=user_id,
            task_id=task_id,
            total_cost=result.total_cost,
            payments_matrix=result.payments_matrix,
            solver_status=result.solver_status,
        )
    finally:
        db.close()
