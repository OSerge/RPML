"""Map persisted user debts + scenario profile to a RiosSolisInstance for RPML."""

from __future__ import annotations

import numpy as np
from rpml.data_loader import RiosSolisInstance

from server.domain.models.loan_type import LoanType, parse_loan_type
from server.infrastructure.db.models.debt import DebtORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM

_PER_LOAN_SOURCE_KEYS = (
    "principals",
    "fixedPayment",
    "minPaymentPct",
    "prepayPenalty",
    "stipulatedAmount",
    "loanTypes",
    "releaseTimeByLoan",
)


class OptimizationInstanceError(ValueError):
    """Raised when debts and scenario profile cannot be mapped to RiosSolisInstance."""


def _loan_bucket(loan_type: str | None) -> int:
    if loan_type is None:
        raise OptimizationInstanceError("Debt loan_type is required for optimization")
    try:
        canonical = parse_loan_type(loan_type)
    except ValueError as exc:
        raise OptimizationInstanceError(str(exc)) from None
    if canonical == LoanType.CAR_LOAN:
        return 0
    if canonical == LoanType.HOUSE_LOAN:
        return 1
    if canonical == LoanType.CREDIT_CARD:
        return 2
    return 3


def _require_canonical_debt_order(debts: list[DebtORM]) -> list[DebtORM]:
    by_id = sorted(debts, key=lambda d: d.id)
    canonical = sorted(debts, key=lambda d: (_loan_bucket(d.loan_type), d.id))
    if by_id != canonical:
        raise OptimizationInstanceError(
            "Debts are not in canonical order (expected cars, then houses, then credit cards, "
            "then bank loans; stable by id within each group)."
        )
    return by_id


def _count_loan_types(ordered: list[DebtORM]) -> tuple[int, int, int, int]:
    buckets = [_loan_bucket(d.loan_type) for d in ordered]
    return (
        sum(1 for b in buckets if b == 0),
        sum(1 for b in buckets if b == 1),
        sum(1 for b in buckets if b == 2),
        sum(1 for b in buckets if b == 3),
    )


def _require_non_null_fields(debt: DebtORM) -> None:
    fields = (
        ("principal", debt.principal),
        ("fixed_payment", debt.fixed_payment),
        ("min_payment_pct", debt.min_payment_pct),
        ("prepay_penalty", debt.prepay_penalty),
        ("interest_rate_monthly", debt.interest_rate_monthly),
        ("default_rate_monthly", debt.default_rate_monthly),
        ("stipulated_amount", debt.stipulated_amount),
        ("release_time", debt.release_time),
    )
    missing = [name for name, val in fields if val is None]
    if missing:
        raise OptimizationInstanceError(
            f"Debt id={debt.id} is missing required fields: {', '.join(missing)}"
        )


def _validate_profile_vectors(
    profile: ScenarioProfileORM,
    *,
    n_loans: int,
    horizon_months: int,
) -> None:
    income = profile.monthly_income_vector
    if not isinstance(income, list):
        raise OptimizationInstanceError("scenario profile monthly_income_vector must be a list")
    if len(income) < horizon_months:
        raise OptimizationInstanceError(
            f"monthly_income_vector length ({len(income)}) is less than horizon_months ({horizon_months})"
        )
    if profile.horizon_months != len(income):
        raise OptimizationInstanceError(
            f"scenario profile horizon_months ({profile.horizon_months}) does not match "
            f"monthly_income_vector length ({len(income)})"
        )

    if profile.source_json is None:
        raise OptimizationInstanceError("scenario profile source_json is required for optimization")
    if not isinstance(profile.source_json, dict):
        raise OptimizationInstanceError("scenario profile source_json must be an object")

    for key in _PER_LOAN_SOURCE_KEYS:
        if key not in profile.source_json:
            raise OptimizationInstanceError(
                f"scenario profile source_json is missing key {key!r}"
            )
        vec = profile.source_json[key]
        if not isinstance(vec, list):
            raise OptimizationInstanceError(f"scenario profile source_json[{key!r}] must be a list")
        if len(vec) != n_loans:
            raise OptimizationInstanceError(
                f"scenario profile source_json[{key!r}] length ({len(vec)}) does not match "
                f"number of debts ({n_loans})"
            )


def build_rios_solis_instance(
    debts: list[DebtORM],
    profile: ScenarioProfileORM,
    horizon_months: int,
    *,
    user_id: int,
) -> RiosSolisInstance:
    """Build a solver instance from debt rows and scenario profile (ordered by id)."""
    if not debts:
        raise OptimizationInstanceError("No debts to optimize")

    ordered = _require_canonical_debt_order(debts)
    n = len(ordered)
    t = horizon_months
    for d in ordered:
        _require_non_null_fields(d)

    _validate_profile_vectors(profile, n_loans=n, horizon_months=t)

    n_cars, n_houses, n_credit_cards, n_bank_loans = _count_loan_types(ordered)

    principals = np.array([float(d.principal) for d in ordered], dtype=float)
    min_payment_pct = np.array([float(d.min_payment_pct) for d in ordered], dtype=float)
    prepay_penalty = np.array([float(d.prepay_penalty) for d in ordered], dtype=float)
    stipulated_amount = np.array([float(d.stipulated_amount) for d in ordered], dtype=float)
    fixed_payment = np.array([float(d.fixed_payment) for d in ordered], dtype=float)
    release_time = np.array([int(d.release_time) for d in ordered], dtype=int)

    ir = np.array([float(d.interest_rate_monthly) for d in ordered], dtype=float)
    dr = np.array([float(d.default_rate_monthly) for d in ordered], dtype=float)
    ones_t = np.ones(t, dtype=float)
    interest_rates = np.outer(ir, ones_t)
    default_rates = np.outer(dr, ones_t)

    monthly_income = np.array(profile.monthly_income_vector[:t], dtype=float)

    return RiosSolisInstance(
        name=f"user-{user_id}",
        n=n,
        T=t,
        n_cars=n_cars,
        n_houses=n_houses,
        n_credit_cards=n_credit_cards,
        n_bank_loans=n_bank_loans,
        principals=principals,
        interest_rates=interest_rates,
        default_rates=default_rates,
        min_payment_pct=min_payment_pct,
        prepay_penalty=prepay_penalty,
        monthly_income=monthly_income,
        release_time=release_time,
        stipulated_amount=stipulated_amount,
        fixed_payment=fixed_payment,
    )
