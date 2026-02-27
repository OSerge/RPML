"""Debts endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_current_user
from app.core.database import get_db
from app.models.debt import Debt
from app.models.user import User
from app.schemas.debt import DebtCreate, DebtResponse, DebtUpdate

router = APIRouter()


def _debt_to_response(debt: Debt) -> DebtResponse:
    return DebtResponse(
        id=str(debt.id),
        name=debt.name,
        principal=float(debt.principal),
        current_balance=float(debt.current_balance),
        interest_rate_annual=float(debt.interest_rate_annual),
        min_payment_pct=float(debt.min_payment_pct),
        late_fee_rate=float(debt.late_fee_rate),
        start_date=debt.start_date,
        term_months=debt.term_months,
    )


@router.get("", response_model=list[DebtResponse])
async def list_debts(
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Debt).where(Debt.user_id == current_user.id))
    debts = result.scalars().all()
    return [_debt_to_response(d) for d in debts]


@router.post("", response_model=DebtResponse)
async def create_debt(
    data: DebtCreate,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    debt = Debt(
        user_id=current_user.id,
        name=data.name,
        principal=data.principal,
        current_balance=data.current_balance,
        interest_rate_annual=data.interest_rate_annual,
        min_payment_pct=data.min_payment_pct,
        late_fee_rate=data.late_fee_rate,
        start_date=data.start_date,
        term_months=data.term_months,
    )
    db.add(debt)
    await db.commit()
    await db.refresh(debt)
    return _debt_to_response(debt)


@router.get("/{debt_id}", response_model=DebtResponse)
async def get_debt(
    debt_id: UUID,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Debt).where(Debt.id == debt_id, Debt.user_id == current_user.id)
    )
    debt = result.scalar_one_or_none()
    if debt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debt not found")
    return _debt_to_response(debt)


@router.patch("/{debt_id}", response_model=DebtResponse)
async def update_debt(
    debt_id: UUID,
    data: DebtUpdate,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Debt).where(Debt.id == debt_id, Debt.user_id == current_user.id)
    )
    debt = result.scalar_one_or_none()
    if debt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debt not found")
    if data.name is not None:
        debt.name = data.name
    if data.current_balance is not None:
        debt.current_balance = data.current_balance
    await db.commit()
    await db.refresh(debt)
    return _debt_to_response(debt)


@router.delete("/{debt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_debt(
    debt_id: UUID,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Debt).where(Debt.id == debt_id, Debt.user_id == current_user.id)
    )
    debt = result.scalar_one_or_none()
    if debt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debt not found")
    await db.delete(debt)
    await db.commit()
