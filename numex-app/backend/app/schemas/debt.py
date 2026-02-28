"""Debt schemas."""

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class DebtTypeEnum(str, Enum):
    CREDIT_CARD = "credit_card"
    MORTGAGE = "mortgage"
    CONSUMER_LOAN = "consumer_loan"
    CAR_LOAN = "car_loan"
    MICROLOAN = "microloan"


class PaymentTypeEnum(str, Enum):
    ANNUITY = "annuity"
    DIFFERENTIATED = "differentiated"
    MINIMUM_PERCENT = "minimum_percent"


class PrepaymentPolicyEnum(str, Enum):
    ALLOWED = "allowed"
    PROHIBITED = "prohibited"
    WITH_PENALTY = "with_penalty"


DEBT_TYPE_DEFAULTS: dict[DebtTypeEnum, dict] = {
    DebtTypeEnum.CREDIT_CARD: {
        "payment_type": PaymentTypeEnum.MINIMUM_PERCENT,
        "prepayment_policy": PrepaymentPolicyEnum.ALLOWED,
        "term_months": None,
        "min_payment_pct": 5.0,
    },
    DebtTypeEnum.MORTGAGE: {
        "payment_type": PaymentTypeEnum.ANNUITY,
        "prepayment_policy": PrepaymentPolicyEnum.WITH_PENALTY,
        "term_months": 240,
        "min_payment_pct": 0,
    },
    DebtTypeEnum.CONSUMER_LOAN: {
        "payment_type": PaymentTypeEnum.ANNUITY,
        "prepayment_policy": PrepaymentPolicyEnum.ALLOWED,
        "term_months": 36,
        "min_payment_pct": 0,
    },
    DebtTypeEnum.CAR_LOAN: {
        "payment_type": PaymentTypeEnum.ANNUITY,
        "prepayment_policy": PrepaymentPolicyEnum.WITH_PENALTY,
        "term_months": 60,
        "min_payment_pct": 0,
    },
    DebtTypeEnum.MICROLOAN: {
        "payment_type": PaymentTypeEnum.ANNUITY,
        "prepayment_policy": PrepaymentPolicyEnum.ALLOWED,
        "term_months": 6,
        "min_payment_pct": 0,
    },
}


class DebtCreate(BaseModel):
    name: str
    debt_type: DebtTypeEnum

    principal: float
    current_balance: float | None = Field(default=None, description="Defaults to principal if omitted")
    interest_rate_annual: float

    payment_type: PaymentTypeEnum | None = None
    min_payment_pct: float | None = None
    fixed_payment: float | None = None

    prepayment_policy: PrepaymentPolicyEnum | None = None
    prepayment_penalty_pct: float | None = None

    late_fee_rate: float = 0
    start_date: date
    term_months: int | None = Field(default=None, description="Not used for credit_card")

    credit_limit: float | None = None
    grace_period_days: int | None = None

    @field_validator("term_months", mode="before")
    @classmethod
    def term_months_allow_none(cls, v: object) -> int | None:
        if v is None:
            return None
        return v

    @model_validator(mode="before")
    @classmethod
    def inject_missing_optionals(cls, data: dict) -> dict:
        if isinstance(data, dict):
            for key in ("current_balance", "term_months"):
                if key not in data:
                    data = {**data, key: None}
        return data

    @model_validator(mode="after")
    def apply_defaults_and_validate(self) -> "DebtCreate":
        defaults = DEBT_TYPE_DEFAULTS.get(self.debt_type, {})

        updates: dict = {}
        if self.current_balance is None:
            updates["current_balance"] = self.principal
        if self.payment_type is None:
            updates["payment_type"] = defaults.get("payment_type", PaymentTypeEnum.ANNUITY)
        if self.prepayment_policy is None:
            updates["prepayment_policy"] = defaults.get("prepayment_policy", PrepaymentPolicyEnum.ALLOWED)
        if self.term_months is None:
            updates["term_months"] = defaults.get("term_months")
        if self.min_payment_pct is None:
            updates["min_payment_pct"] = defaults.get("min_payment_pct", 0)
        if self.debt_type == DebtTypeEnum.CREDIT_CARD and self.credit_limit is None:
            updates["credit_limit"] = self.principal
        if self.prepayment_policy == PrepaymentPolicyEnum.WITH_PENALTY and self.prepayment_penalty_pct is None:
            updates["prepayment_penalty_pct"] = 1.0

        if not updates:
            return self
        return self.model_copy(update=updates)


class DebtUpdate(BaseModel):
    name: str | None = None
    current_balance: float | None = None
    interest_rate_annual: float | None = None
    min_payment_pct: float | None = None
    fixed_payment: float | None = None
    prepayment_policy: PrepaymentPolicyEnum | None = None
    prepayment_penalty_pct: float | None = None
    term_months: int | None = None
    credit_limit: float | None = None
    grace_period_days: int | None = None


class DebtResponse(BaseModel):
    id: str
    name: str
    debt_type: DebtTypeEnum

    principal: float
    current_balance: float
    interest_rate_annual: float

    payment_type: PaymentTypeEnum
    min_payment_pct: float
    fixed_payment: float | None

    prepayment_policy: PrepaymentPolicyEnum
    prepayment_penalty_pct: float | None

    late_fee_rate: float | None
    start_date: date
    term_months: int | None

    credit_limit: float | None
    grace_period_days: int | None

    model_config = {"from_attributes": True}


DEBT_TYPE_LABELS: dict[DebtTypeEnum, str] = {
    DebtTypeEnum.CREDIT_CARD: "Кредитная карта",
    DebtTypeEnum.MORTGAGE: "Ипотека",
    DebtTypeEnum.CONSUMER_LOAN: "Потребительский кредит",
    DebtTypeEnum.CAR_LOAN: "Автокредит",
    DebtTypeEnum.MICROLOAN: "Микрозайм",
}
