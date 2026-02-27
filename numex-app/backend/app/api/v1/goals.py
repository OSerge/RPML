"""Financial goals endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_current_user
from app.core.database import get_db
from app.models.goal import Goal
from app.models.user import User

router = APIRouter()


@router.get("")
async def list_goals(
    current_user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Goal).where(Goal.user_id == current_user.id))
    goals = result.scalars().all()
    return [
        {
            "id": str(g.id),
            "name": g.name,
            "target_amount": float(g.target_amount),
            "target_date": g.target_date.isoformat(),
        }
        for g in goals
    ]
