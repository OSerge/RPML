"""Auth endpoints. With Supabase: use Supabase Auth on frontend; /me validates JWT."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_current_user
from app.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, Token, UserCreate, UserResponse

router = APIRouter()


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(id=str(user.id), email=user.email)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(require_current_user)):
    """Return current user (validates Supabase or legacy JWT)."""
    return _user_to_response(current_user)


@router.post("/register", response_model=UserResponse)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    if settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use Supabase Auth for registration",
        )
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    user = User(
        email=data.email,
        password_hash=get_password_hash(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_to_response(user)


@router.post("/login", response_model=Token)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    if settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use Supabase Auth for login",
        )
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=30),
    )
    return Token(access_token=access_token)
