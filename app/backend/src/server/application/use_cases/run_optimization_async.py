"""Enqueue and process async optimization jobs (Celery worker)."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass

from rpml.income_monte_carlo import IncomeMCConfig

from sqlalchemy.orm import Session

from server.application.use_cases.run_optimization_sync import (
    SCENARIO_INPUT_MODE,
    OptimizationSolverFailed,
    _resolve_optimization_input,
    execute_run_optimization_sync,
)
from server.infrastructure.rpml_adapter.instance_builder import OptimizationInstanceError
from server.infrastructure.db.models.optimization_plan import OptimizationPlanORM
from server.infrastructure.db.models.optimization_task import OptimizationTaskORM


@dataclass(frozen=True)
class CreateAsyncTaskResult:
    task_id: str
    status: str = "pending"
    input_mode: str = SCENARIO_INPUT_MODE
    horizon_months: int = 1
    instance_name: str | None = None
    ru_mode: bool = True
    mc_income: bool = False


def execute_create_async_optimization_task(
    db: Session,
    user_id: int,
    horizon_months: int | None,
    *,
    input_mode: str = SCENARIO_INPUT_MODE,
    instance_name: str | None = None,
    ru_mode: bool = True,
    mc_income: bool = False,
    mc_config: IncomeMCConfig | None = None,
) -> CreateAsyncTaskResult:
    task_id = str(uuid.uuid4())
    preview = _resolve_optimization_input(
        db,
        user_id=user_id,
        horizon_months=horizon_months,
        input_mode=input_mode,
        instance_name=instance_name,
    )
    row = OptimizationTaskORM(
        celery_task_id=task_id,
        user_id=user_id,
        status="pending",
        horizon_months=preview.horizon_months,
        input_mode=preview.input_mode,
        instance_name=preview.instance_name,
        ru_mode=ru_mode,
        mc_income=mc_income,
        mc_config_json=asdict(mc_config) if mc_config is not None else None,
        plan_id=None,
        error_message=None,
    )
    db.add(row)
    db.commit()
    from server.infrastructure.queue.tasks import run_optimization_task

    run_optimization_task.apply_async(args=(), task_id=task_id)
    return CreateAsyncTaskResult(
        task_id=task_id,
        input_mode=preview.input_mode,
        horizon_months=preview.horizon_months,
        instance_name=preview.instance_name,
        ru_mode=ru_mode,
        mc_income=mc_income,
    )


@dataclass(frozen=True)
class TaskStatusResult:
    status: str
    task_id: str
    plan_id: str | None
    error: str | None
    input_mode: str
    horizon_months: int
    instance_name: str | None
    ru_mode: bool
    mc_income: bool


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
        input_mode=row.input_mode,
        horizon_months=int(row.horizon_months),
        instance_name=row.instance_name,
        ru_mode=bool(row.ru_mode),
        mc_income=bool(row.mc_income),
    )


def _persist_completed_plan(
    db: Session,
    *,
    user_id: int,
    task_id: str,
    total_cost: float,
    result_json: dict,
    baseline_comparison_json: dict,
    payments_matrix: list[list[float]],
    horizon_months: int,
    solver_status: str,
    input_mode: str,
    assumptions: list[str],
    instance_name: str | None,
    ru_mode: bool,
    mc_income: bool,
    mc_summary: dict | None,
    mc_config: IncomeMCConfig | None,
) -> None:
    plan_id = str(uuid.uuid4())
    plan = OptimizationPlanORM(
        id=plan_id,
        user_id=user_id,
        total_cost=total_cost,
        result_json=result_json,
        baseline_comparison_json=baseline_comparison_json,
        payments_matrix=payments_matrix,
        horizon_months=horizon_months,
        solver_status=solver_status,
        input_mode=input_mode,
        instance_name=instance_name,
        assumptions=assumptions,
        ru_mode=ru_mode,
        mc_income=mc_income,
        mc_summary=mc_summary,
        mc_config_json=asdict(mc_config) if mc_config is not None else None,
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
        input_mode = task.input_mode
        instance_name = task.instance_name
        ru_mode = bool(task.ru_mode)
        mc_income = bool(task.mc_income)
        mc_config = (
            IncomeMCConfig(**task.mc_config_json)
            if isinstance(task.mc_config_json, dict)
            else None
        )
        try:
            result = execute_run_optimization_sync(
                db,
                user_id,
                horizon,
                mode="async",
                input_mode=input_mode,
                instance_name=instance_name,
                ru_mode=ru_mode,
                mc_income=mc_income,
                mc_config=mc_config,
            )
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
            result_json={
                "status": result.solver_status,
                "total_cost": result.total_cost,
                "debts": result.debt_summaries,
                "payments_matrix": result.payments_matrix,
                "balances_matrix": result.balances_matrix,
                "savings_vector": result.savings_vector,
                "horizon_months": result.horizon_months,
                "input_mode": result.input_mode,
                "assumptions": result.assumptions,
                "instance_name": result.instance_name,
                "ru_mode": result.ru_mode,
                "mc_income": result.mc_income,
                "mc_summary": result.mc_summary,
                "mc_config": (
                    asdict(result.mc_config) if result.mc_config is not None else None
                ),
                "budget_policy": result.budget_policy,
                "budget_trace": result.budget_trace,
            },
            baseline_comparison_json=result.baseline_comparison,
            payments_matrix=result.payments_matrix,
            horizon_months=result.horizon_months,
            solver_status=result.solver_status,
            input_mode=result.input_mode,
            assumptions=result.assumptions,
            instance_name=result.instance_name,
            ru_mode=result.ru_mode,
            mc_income=result.mc_income,
            mc_summary=result.mc_summary,
            mc_config=result.mc_config,
        )
    finally:
        db.close()
