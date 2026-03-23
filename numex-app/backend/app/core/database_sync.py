"""Synchronous database session for Celery tasks.

Celery tasks run in sync context, so we need a sync SQLAlchemy session.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

sync_engine = create_engine(
    settings.database_url_sync,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SyncSession = sessionmaker(
    sync_engine,
    autocommit=False,
    autoflush=False,
)
