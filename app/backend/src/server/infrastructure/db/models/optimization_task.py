from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from server.infrastructure.db.base import Base


class OptimizationTaskORM(Base):
    __tablename__ = "optimization_tasks"

    celery_task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("optimization_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
