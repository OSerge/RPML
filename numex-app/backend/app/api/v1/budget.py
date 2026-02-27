"""Budget and transactions endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_current_user
from app.core.database import get_db
from app.models.transaction import Transaction
from app.models.user import User

router = APIRouter()


class TransactionCreate(BaseModel):
    amount: float
    category: str
    date: date
    description: str | None = None


@router.post("/transactions")
async def create_transaction(
    data: TransactionCreate,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    txn = Transaction(
        user_id=current_user.id,
        amount=data.amount,
        category=data.category,
        date=data.date,
        description=data.description,
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return {"id": str(txn.id), "amount": float(txn.amount), "category": txn.category}


@router.get("/summary")
async def budget_summary(
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction).where(Transaction.user_id == current_user.id)
    )
    transactions = result.scalars().all()
    total_income = sum(t.amount for t in transactions if t.amount > 0)
    total_expense = sum(-t.amount for t in transactions if t.amount < 0)
    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": total_income + total_expense,
    }


@router.get("/transactions")
async def list_transactions(
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
):
    q = select(Transaction).where(Transaction.user_id == current_user.id)
    if from_date:
        q = q.where(Transaction.date >= from_date)
    if to_date:
        q = q.where(Transaction.date <= to_date)
    q = q.order_by(Transaction.date.desc())
    result = await db.execute(q)
    transactions = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "amount": float(t.amount),
            "category": t.category,
            "date": t.date.isoformat(),
            "description": t.description,
        }
        for t in transactions
    ]
