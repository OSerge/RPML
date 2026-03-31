from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.domain.models.loan_type import LoanType, loan_type_values, parse_loan_type


class DebtCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    loan_type: LoanType
    principal: float | None = None
    fixed_payment: float | None = None
    min_payment_pct: float | None = None
    prepay_penalty: float | None = None
    interest_rate_monthly: float | None = None
    default_rate_monthly: float | None = None
    stipulated_amount: float | None = None
    release_time: int | None = None

    @field_validator("loan_type", mode="before")
    @classmethod
    def _normalize_loan_type(cls, value: object) -> LoanType:
        if isinstance(value, LoanType):
            return value
        if isinstance(value, str):
            return parse_loan_type(value)
        raise ValueError(
            f"Unsupported loan_type type: expected string, got {type(value).__name__}"
        )


class DebtUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    loan_type: LoanType | None = None
    principal: float | None = None
    fixed_payment: float | None = None
    min_payment_pct: float | None = None
    prepay_penalty: float | None = None
    interest_rate_monthly: float | None = None
    default_rate_monthly: float | None = None
    stipulated_amount: float | None = None
    release_time: int | None = None

    @field_validator("loan_type", mode="before")
    @classmethod
    def _normalize_loan_type(cls, value: object) -> LoanType | None:
        if value is None:
            return None
        if isinstance(value, LoanType):
            return value
        if isinstance(value, str):
            return parse_loan_type(value)
        raise ValueError(
            f"Unsupported loan_type type: expected string/null, got {type(value).__name__}"
        )


class DebtRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    loan_type: LoanType | None = None
    principal: float | None = None
    fixed_payment: float | None = None
    min_payment_pct: float | None = None
    prepay_penalty: float | None = None
    interest_rate_monthly: float | None = None
    default_rate_monthly: float | None = None
    stipulated_amount: float | None = None
    release_time: int | None = None


class LoanTypeDirectory(BaseModel):
    supported_values: tuple[str, ...] = Field(default_factory=loan_type_values)
