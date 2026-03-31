from __future__ import annotations

from enum import StrEnum


class LoanType(StrEnum):
    CAR_LOAN = "car_loan"
    HOUSE_LOAN = "house_loan"
    CREDIT_CARD = "credit_card"
    BANK_LOAN = "bank_loan"


_LOAN_TYPE_ALIASES: dict[str, LoanType] = {
    "car": LoanType.CAR_LOAN,
    "car_loan": LoanType.CAR_LOAN,
    "auto": LoanType.CAR_LOAN,
    "auto_loan": LoanType.CAR_LOAN,
    "house": LoanType.HOUSE_LOAN,
    "house_loan": LoanType.HOUSE_LOAN,
    "home": LoanType.HOUSE_LOAN,
    "home_loan": LoanType.HOUSE_LOAN,
    "mortgage": LoanType.HOUSE_LOAN,
    "credit_card": LoanType.CREDIT_CARD,
    "credit": LoanType.CREDIT_CARD,
    "card": LoanType.CREDIT_CARD,
    "cc": LoanType.CREDIT_CARD,
    "bank_loan": LoanType.BANK_LOAN,
    "bank": LoanType.BANK_LOAN,
    "loan": LoanType.BANK_LOAN,
}


def parse_loan_type(value: str) -> LoanType:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _LOAN_TYPE_ALIASES:
        return _LOAN_TYPE_ALIASES[normalized]
    raise ValueError(
        f"Unsupported loan_type={value!r}. Allowed values: {', '.join(loan_type_values())}"
    )


def loan_type_values() -> tuple[str, ...]:
    return tuple(t.value for t in LoanType)
