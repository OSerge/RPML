"""Debt model."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Debt(Base):
    __tablename__ = "debts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    principal: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    current_balance: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    interest_rate_annual: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    min_payment_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    late_fee_rate: Mapped[float] = mapped_column(Numeric(6, 4), default=0, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    term_months: Mapped[int] = mapped_column(nullable=False)

    user = relationship("User", back_populates="debts")
