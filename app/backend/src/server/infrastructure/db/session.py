from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from server.config.settings import settings
from server.infrastructure.db.base import Base
from server.infrastructure.db.models import user as _user_models  # noqa: F401
from server.infrastructure.db.models import debt as _debt_models  # noqa: F401
from server.infrastructure.db.models import optimization_plan as _opt_plan_models  # noqa: F401
from server.infrastructure.db.models import optimization_task as _opt_task_models  # noqa: F401

_engine_kwargs: dict = {}
if settings.database_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
