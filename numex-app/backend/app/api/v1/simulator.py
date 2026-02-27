"""Simulator endpoints for generating synthetic data."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.simulator import OpenBankingSimulator, UserProfile

router = APIRouter()


@router.post("/generate")
async def generate_synthetic_data(
    months: int = 6,
    loans_count: int = 2,
    monthly_income: float = 80000,
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate synthetic transactions and loans for the current user."""
    profile = UserProfile(monthly_income=monthly_income)
    simulator = OpenBankingSimulator(profile)

    transactions = simulator.generate_transactions(current_user.id, months=months)
    loans = simulator.generate_loans(current_user.id, count=loans_count)

    for t in transactions:
        db.add(t)
    for d in loans:
        db.add(d)
    await db.commit()

    return {
        "transactions_created": len(transactions),
        "loans_created": len(loans),
    }
