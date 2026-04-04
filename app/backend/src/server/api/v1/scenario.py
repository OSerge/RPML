from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.api.deps import get_current_user
from server.domain.models.user import UserRead
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM
from server.infrastructure.db.session import get_db

router = APIRouter()


class ScenarioProfileResponse(BaseModel):
    id: int
    code: str
    horizon_months: int
    monthly_income_vector: list[float]
    baseline_reference: dict[str, Any] | list[Any] | None = None


class ScenarioProfileUpdateRequest(BaseModel):
    horizon_months: int | None = Field(
        default=None,
        ge=1,
        le=240,
        description="Горизонт планирования в месяцах.",
    )
    monthly_income_vector: list[float] | None = Field(
        default=None,
        description="Вектор доступного бюджета на погашение по месяцам.",
    )


class AvailableBudgetEstimateRequest(BaseModel):
    horizon_months: int = Field(
        ...,
        ge=1,
        le=240,
        description="Горизонт планирования в месяцах.",
    )
    monthly_income: float = Field(..., ge=0, description="Средний месячный доход пользователя.")
    mandatory_expenses: float = Field(..., ge=0, description="Обязательные ежемесячные расходы.")
    variable_expenses: float = Field(
        default=0,
        ge=0,
        description="Прочие переменные ежемесячные расходы.",
    )
    safety_buffer_pct: float = Field(
        default=0.1,
        ge=0,
        le=1,
        description="Доля защитного буфера (0..1), не направляемая в погашение.",
    )


class AvailableBudgetEstimateResponse(BaseModel):
    monthly_available_budget: float
    scenario_profile: ScenarioProfileResponse


def _to_profile_response(row: ScenarioProfileORM) -> ScenarioProfileResponse:
    return ScenarioProfileResponse(
        id=row.id,
        code=row.code,
        horizon_months=row.horizon_months,
        monthly_income_vector=[float(x) for x in row.monthly_income_vector],
        baseline_reference=row.baseline_reference,
    )


def _get_latest_profile(db: Session, user_id: int) -> ScenarioProfileORM | None:
    return db.scalars(
        select(ScenarioProfileORM)
        .where(ScenarioProfileORM.user_id == user_id)
        .order_by(ScenarioProfileORM.id.desc())
    ).first()


@router.get(
    "/profile",
    response_model=ScenarioProfileResponse,
    summary="Получить активный профиль дохода",
    description="Возвращает текущий сценарный профиль дохода пользователя (последний по времени).",
    responses={401: {"description": "Пользователь не аутентифицирован."}, 404: {"description": "Профиль не найден."}},
)
def get_profile(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> ScenarioProfileResponse:
    row = _get_latest_profile(db, current_user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario profile not found")
    return _to_profile_response(row)


@router.put(
    "/profile",
    response_model=ScenarioProfileResponse,
    summary="Обновить профиль дохода",
    description="Обновляет вектор доступного бюджета. Если профиль отсутствует, создается новый.",
    responses={401: {"description": "Пользователь не аутентифицирован."}, 422: {"description": "Ошибка валидации."}},
)
def upsert_profile(
    body: ScenarioProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> ScenarioProfileResponse:
    row = _get_latest_profile(db, current_user.id)
    if row is None:
        row = ScenarioProfileORM(
            user_id=current_user.id,
            code="manual",
            horizon_months=12,
            monthly_income_vector=[0.0] * 12,
            source_json=None,
            baseline_reference={"origin": "manual"},
        )
        db.add(row)
        db.flush()

    current_vector = [float(x) for x in row.monthly_income_vector]
    new_horizon = body.horizon_months if body.horizon_months is not None else row.horizon_months

    if body.monthly_income_vector is not None:
        if len(body.monthly_income_vector) != new_horizon:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"monthly_income_vector length ({len(body.monthly_income_vector)}) "
                    f"must match horizon_months ({new_horizon})"
                ),
            )
        row.monthly_income_vector = [float(x) for x in body.monthly_income_vector]
    else:
        if len(current_vector) >= new_horizon:
            row.monthly_income_vector = current_vector[:new_horizon]
        else:
            last_value = current_vector[-1] if current_vector else 0.0
            row.monthly_income_vector = current_vector + [last_value] * (new_horizon - len(current_vector))

    row.horizon_months = int(new_horizon)
    if not isinstance(row.baseline_reference, dict):
        row.baseline_reference = {}
    row.baseline_reference = {
        **row.baseline_reference,
        "origin": "manual",
    }
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_profile_response(row)


@router.post(
    "/profile/estimate-available-budget",
    response_model=AvailableBudgetEstimateResponse,
    summary="Оценить доступный бюджет на погашение",
    description=(
        "Рассчитывает доступный бюджет как `(income - mandatory - variable) * (1 - safety_buffer_pct)` "
        "и записывает его как равномерный monthly_income_vector."
    ),
    responses={401: {"description": "Пользователь не аутентифицирован."}, 422: {"description": "Ошибка валидации."}},
)
def estimate_available_budget(
    body: AvailableBudgetEstimateRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> AvailableBudgetEstimateResponse:
    gross_available = float(body.monthly_income) - float(body.mandatory_expenses) - float(body.variable_expenses)
    protected_available = max(gross_available, 0.0) * (1.0 - float(body.safety_buffer_pct))
    vector = [float(protected_available)] * int(body.horizon_months)

    profile = upsert_profile(
        ScenarioProfileUpdateRequest(
            horizon_months=body.horizon_months,
            monthly_income_vector=vector,
        ),
        db=db,
        current_user=current_user,
    )
    return AvailableBudgetEstimateResponse(
        monthly_available_budget=float(protected_available),
        scenario_profile=profile,
    )
