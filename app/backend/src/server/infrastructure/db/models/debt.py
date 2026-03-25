from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.infrastructure.db.base import Base


class DebtORM(Base):
    __tablename__ = "debts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    loan_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    principal: Mapped[float | None] = mapped_column(Float, nullable=True)
    fixed_payment: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_payment_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    prepay_penalty: Mapped[float | None] = mapped_column(Float, nullable=True)
    interest_rate_monthly: Mapped[float | None] = mapped_column(Float, nullable=True)
    default_rate_monthly: Mapped[float | None] = mapped_column(Float, nullable=True)
    stipulated_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    release_time: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["UserORM"] = relationship("UserORM", back_populates="debts")
