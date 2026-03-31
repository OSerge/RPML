from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from server.infrastructure.db.base import Base


class OptimizationPlanORM(Base):
    __tablename__ = "optimization_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    total_cost: Mapped[float] = mapped_column()
    payments_matrix: Mapped[list] = mapped_column(JSON, nullable=False)
    solver_status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_mode: Mapped[str] = mapped_column(String(64), nullable=False, default="scenario_snapshot")
    assumptions: Mapped[list] = mapped_column(JSON, nullable=False)
