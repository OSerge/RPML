"""Debt model."""

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DebtType(str, enum.Enum):
    """Type of debt instrument."""
    CREDIT_CARD = "credit_card"
    MORTGAGE = "mortgage"
    CONSUMER_LOAN = "consumer_loan"
    CAR_LOAN = "car_loan"
    MICROLOAN = "microloan"


class PaymentType(str, enum.Enum):
    """Payment schedule type for installment loans."""
    ANNUITY = "annuity"
    DIFFERENTIATED = "differentiated"
    MINIMUM_PERCENT = "minimum_percent"


class PrepaymentPolicy(str, enum.Enum):
    """Prepayment (early repayment) policy."""
    ALLOWED = "allowed"
    PROHIBITED = "prohibited"
    WITH_PENALTY = "with_penalty"


DEBT_TYPE_DEFAULTS = {
    DebtType.CREDIT_CARD: {
        "payment_type": PaymentType.MINIMUM_PERCENT,
        "prepayment_policy": PrepaymentPolicy.ALLOWED,
        "term_months": None,
    },
    DebtType.MORTGAGE: {
        "payment_type": PaymentType.ANNUITY,
        "prepayment_policy": PrepaymentPolicy.WITH_PENALTY,
        "term_months": 240,
    },
    DebtType.CONSUMER_LOAN: {
        "payment_type": PaymentType.ANNUITY,
        "prepayment_policy": PrepaymentPolicy.ALLOWED,
        "term_months": 36,
    },
    DebtType.CAR_LOAN: {
        "payment_type": PaymentType.ANNUITY,
        "prepayment_policy": PrepaymentPolicy.WITH_PENALTY,
        "term_months": 60,
    },
    DebtType.MICROLOAN: {
        "payment_type": PaymentType.ANNUITY,
        "prepayment_policy": PrepaymentPolicy.ALLOWED,
        "term_months": 6,
    },
}


class Debt(Base):
    __tablename__ = "debts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    debt_type: Mapped[DebtType] = mapped_column(
        Enum(DebtType, name="debt_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DebtType.CONSUMER_LOAN,
    )

    principal: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    current_balance: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    interest_rate_annual: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)

    payment_type: Mapped[PaymentType] = mapped_column(
        Enum(PaymentType, name="payment_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PaymentType.ANNUITY,
    )
    min_payment_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    fixed_payment: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)

    prepayment_policy: Mapped[PrepaymentPolicy] = mapped_column(
        Enum(PrepaymentPolicy, name="prepayment_policy_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PrepaymentPolicy.ALLOWED,
    )
    prepayment_penalty_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)

    late_fee_rate: Mapped[float] = mapped_column(Numeric(6, 4), default=0, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)

    credit_limit: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    grace_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user = relationship("User", back_populates="debts")
