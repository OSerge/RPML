"""API dependencies."""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token, decode_supabase_jwt
from app.models.user import User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User | None:
    if credentials is None:
        return None
    token = credentials.credentials

    if settings.supabase_jwt_secret:
        payload = decode_supabase_jwt(token)
    else:
        payload = decode_access_token(token)

    if payload is None:
        return None
    user_id = payload.get("sub")
    if user_id is None:
        return None
    try:
        uid = UUID(user_id)
    except (ValueError, TypeError):
        return None

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()

    if user is not None:
        return user

    if settings.supabase_jwt_secret and payload.get("email"):
        user = User(
            id=uid,
            email=payload["email"],
            password_hash="",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    return None


async def require_current_user(
    current_user: User | None = Depends(get_current_user),
) -> User:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return current_user
