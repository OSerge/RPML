"""OptimizationPlan model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class OptimizationPlan(Base):
    __tablename__ = "optimization_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    payments_matrix: Mapped[dict] = mapped_column(JSONB, nullable=False)
    explanations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total_cost: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    savings_vs_minimum: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="optimization_plans")
