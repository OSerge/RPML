from sqlalchemy import select
from sqlalchemy.orm import Session

from server.infrastructure.auth.password import hash_password
from server.infrastructure.db.models.user import UserORM


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_email(self, email: str) -> UserORM | None:
        return self._session.scalars(select(UserORM).where(UserORM.email == email)).first()

    def get_by_id(self, user_id: int) -> UserORM | None:
        return self._session.get(UserORM, user_id)

    def create(self, email: str, password: str) -> UserORM:
        user = UserORM(email=email, hashed_password=hash_password(password))
        self._session.add(user)
        self._session.flush()
        return user
