from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from server.domain.models.user import TokenResponse, UserLogin
from server.infrastructure.auth.jwt_provider import create_access_token
from server.infrastructure.auth.password import DUMMY_PASSWORD_HASH, verify_password
from server.infrastructure.db.session import get_db
from server.infrastructure.repositories.user_repository import UserRepository

router = APIRouter()


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход пользователя",
    description="Проверяет email/пароль и возвращает JWT access token для защищенных эндпоинтов API.",
    responses={
        401: {"description": "Неверный email или пароль."},
    },
)
def login(body: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    repo = UserRepository(db)
    user = repo.get_by_email(body.email)
    stored_hash = user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
    password_ok = verify_password(body.password, stored_hash)
    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)
