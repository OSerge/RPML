"""Debt schemas."""

from datetime import date

from pydantic import BaseModel


class DebtCreate(BaseModel):
    name: str
    principal: float
    current_balance: float
    interest_rate_annual: float
    min_payment_pct: float
    late_fee_rate: float = 0
    start_date: date
    term_months: int


class DebtUpdate(BaseModel):
    name: str | None = None
    current_balance: float | None = None


class DebtResponse(BaseModel):
    id: str
    name: str
    principal: float
    current_balance: float
    interest_rate_annual: float
    min_payment_pct: float
    late_fee_rate: float
    start_date: date
    term_months: int

    model_config = {"from_attributes": True}
