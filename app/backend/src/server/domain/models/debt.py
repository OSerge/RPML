from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.domain.models.loan_type import LoanType, loan_type_values, parse_loan_type


class DebtCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Название кредита/долга в пользовательском интерфейсе.",
    )
    loan_type: LoanType = Field(
        ...,
        description="Тип кредита (влияет на канонический порядок в RPML instance).",
    )
    principal: float | None = Field(
        default=None,
        description="Текущий остаток основного долга.",
    )
    fixed_payment: float | None = Field(
        default=None,
        description="Фиксированный обязательный платеж в месяц.",
    )
    min_payment_pct: float | None = Field(
        default=None,
        description="Минимальный платеж как доля от остатка (0..1).",
    )
    prepay_penalty: float | None = Field(
        default=None,
        description="Штраф за досрочное погашение.",
    )
    interest_rate_monthly: float | None = Field(
        default=None,
        description="Процентная ставка в месяц.",
    )
    default_rate_monthly: float | None = Field(
        default=None,
        description="Ставка штрафа/просрочки в месяц.",
    )
    stipulated_amount: float | None = Field(
        default=None,
        description="Договорная сумма платежа (stated monthly amount).",
    )
    release_time: int | None = Field(
        default=None,
        description="Месяц выдачи кредита (0-indexed).",
    )

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
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Новое название кредита/долга.",
    )
    loan_type: LoanType | None = Field(
        default=None,
        description="Новый тип кредита.",
    )
    principal: float | None = Field(default=None, description="Новый остаток долга.")
    fixed_payment: float | None = Field(default=None, description="Новый фиксированный платеж.")
    min_payment_pct: float | None = Field(default=None, description="Новый min payment в долях.")
    prepay_penalty: float | None = Field(default=None, description="Новый штраф за досрочное погашение.")
    interest_rate_monthly: float | None = Field(default=None, description="Новая ставка в месяц.")
    default_rate_monthly: float | None = Field(default=None, description="Новая штрафная ставка в месяц.")
    stipulated_amount: float | None = Field(default=None, description="Новая договорная сумма платежа.")
    release_time: int | None = Field(default=None, description="Новый месяц выдачи (0-indexed).")

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

    id: int = Field(..., description="Идентификатор записи долга.")
    user_id: int = Field(..., description="Владелец долга.")
    name: str = Field(..., description="Название долга.")
    loan_type: LoanType | None = Field(default=None, description="Тип кредита.")
    principal: float | None = Field(default=None, description="Остаток основного долга.")
    fixed_payment: float | None = Field(default=None, description="Фиксированный месячный платеж.")
    min_payment_pct: float | None = Field(default=None, description="Минимальный платеж в долях.")
    prepay_penalty: float | None = Field(default=None, description="Штраф за досрочное погашение.")
    interest_rate_monthly: float | None = Field(default=None, description="Процентная ставка в месяц.")
    default_rate_monthly: float | None = Field(default=None, description="Ставка штрафа в месяц.")
    stipulated_amount: float | None = Field(default=None, description="Договорная сумма платежа.")
    release_time: int | None = Field(default=None, description="Месяц выдачи (0-indexed).")


class LoanTypeDirectory(BaseModel):
    supported_values: tuple[str, ...] = Field(
        default_factory=loan_type_values,
        description="Список поддерживаемых значений loan_type.",
    )
