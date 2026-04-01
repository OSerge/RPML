from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from server.api.deps import get_current_user
from server.domain.models.debt import DebtRead
from server.domain.models.user import UserRead
from server.infrastructure.db.models.optimization_run import OptimizationRunORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM
from server.infrastructure.db.session import get_db
from server.infrastructure.repositories.debt_repository import DebtRepository

router = APIRouter()
_NON_DISPLAYABLE_FIXED_PAYMENT_MIN = 1e11


class DashboardKpis(BaseModel):
    total_principal: float
    monthly_required_payment: float
    active_debts: int
    last_run_status: str | None = None


class DashboardResponse(BaseModel):
    kpis: DashboardKpis
    debts: list[DebtRead]
    baseline_reference: dict | None = None
    last_optimization: dict | None = None
    scenario: dict | None = None


def _effective_monthly_required_payment(value: float | None) -> float:
    amount = float(value or 0.0)
    if amount >= _NON_DISPLAYABLE_FIXED_PAYMENT_MIN:
        return 0.0
    return amount


@router.get(
    "",
    response_model=DashboardResponse,
    summary="Данные дашборда",
    description=(
        "Возвращает агрегированные KPI, список долгов, актуальный сценарий и "
        "последний результат оптимизации для текущего пользователя."
    ),
    responses={
        401: {"description": "Пользователь не аутентифицирован."},
    },
)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> DashboardResponse:
    repo = DebtRepository(db)
    debts = repo.list_for_user(current_user.id)

    profile = db.scalars(
        select(ScenarioProfileORM)
        .where(ScenarioProfileORM.user_id == current_user.id)
        .order_by(ScenarioProfileORM.id.desc())
    ).first()
    last_run = db.scalars(
        select(OptimizationRunORM)
        .where(OptimizationRunORM.user_id == current_user.id)
        .order_by(desc(OptimizationRunORM.id))
    ).first()

    total_principal = float(sum((d.principal or 0.0) for d in debts))
    monthly_required_payment = float(
        sum(_effective_monthly_required_payment(d.fixed_payment) for d in debts)
    )
    kpis = DashboardKpis(
        total_principal=total_principal,
        monthly_required_payment=monthly_required_payment,
        active_debts=len(debts),
        last_run_status=last_run.status if last_run else None,
    )
    scenario_payload = (
        {
            "id": profile.id,
            "code": profile.code,
            "horizon_months": profile.horizon_months,
            "monthly_income_vector": profile.monthly_income_vector,
        }
        if profile
        else None
    )

    return DashboardResponse(
        kpis=kpis,
        debts=[DebtRead.model_validate(d) for d in debts],
        baseline_reference=profile.baseline_reference if profile else None,
        last_optimization={
            "id": last_run.id,
            "mode": last_run.mode,
            "status": last_run.status,
            "result_json": last_run.result_json,
            "baseline_comparison_json": last_run.baseline_comparison_json,
        }
        if last_run
        else None,
        scenario=scenario_payload,
    )
