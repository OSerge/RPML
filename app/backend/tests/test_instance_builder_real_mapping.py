"""Tests for mapping Debt ORM + ScenarioProfile to RiosSolisInstance."""

from __future__ import annotations

import numpy as np
import pytest

from server.infrastructure.db.models.debt import DebtORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM
from server.infrastructure.rpml_adapter.instance_builder import (
    OptimizationInstanceError,
    build_rios_solis_instance,
)


def _profile_and_debts(
    *,
    principals: tuple[float, float],
    income_len: int = 3,
) -> tuple[list[DebtORM], ScenarioProfileORM]:
    p1, p2 = principals
    debts = [
        DebtORM(
            id=1,
            user_id=1,
            name="loan_0",
            loan_type="bank_loan",
            principal=p1,
            fixed_payment=11.0,
            min_payment_pct=0.12,
            prepay_penalty=1.0,
            interest_rate_monthly=0.013,
            default_rate_monthly=0.014,
            stipulated_amount=50.0,
            release_time=0,
        ),
        DebtORM(
            id=2,
            user_id=1,
            name="loan_1",
            loan_type="bank_loan",
            principal=p2,
            fixed_payment=22.0,
            min_payment_pct=0.22,
            prepay_penalty=2.0,
            interest_rate_monthly=0.015,
            default_rate_monthly=0.016,
            stipulated_amount=60.0,
            release_time=1,
        ),
    ]
    income = [float(i + 1) for i in range(income_len)]
    profile = ScenarioProfileORM(
        user_id=1,
        code="unit",
        horizon_months=income_len,
        monthly_income_vector=income,
        source_json={
            "principals": [p1, p2],
            "fixedPayment": [11.0, 22.0],
            "minPaymentPct": [0.12, 0.22],
            "prepayPenalty": [1.0, 2.0],
            "stipulatedAmount": [50.0, 60.0],
            "loanTypes": ["bank_loan", "bank_loan"],
            "releaseTimeByLoan": [0, 1],
        },
        baseline_reference=None,
    )
    return debts, profile


def test_builder_uses_real_debt_fields_and_income_vector() -> None:
    """Principals and budget must come from ORM fields, not synthetic id-based defaults."""
    debts, profile = _profile_and_debts(principals=(10.0, 20.0))
    t = 3
    inst = build_rios_solis_instance(debts, profile, t, user_id=1)

    np.testing.assert_array_equal(inst.principals, np.array([10.0, 20.0]))
    np.testing.assert_array_equal(inst.fixed_payment, np.array([11.0, 22.0]))
    np.testing.assert_array_equal(inst.min_payment_pct, np.array([0.12, 0.22]))
    np.testing.assert_array_equal(inst.prepay_penalty, np.array([1.0, 2.0]))
    np.testing.assert_array_equal(inst.stipulated_amount, np.array([50.0, 60.0]))
    np.testing.assert_array_equal(inst.release_time, np.array([0, 1]))

    assert inst.T == t
    np.testing.assert_array_equal(inst.monthly_income, np.array([1.0, 2.0, 3.0]))

    assert inst.interest_rates.shape == (2, t)
    assert np.allclose(inst.interest_rates[0, :], 0.013)
    assert np.allclose(inst.interest_rates[1, :], 0.015)
    assert np.allclose(inst.default_rates[0, :], 0.014)
    assert np.allclose(inst.default_rates[1, :], 0.016)

    synthetic_wrong = np.array([500.0 + 100.0 * float(d.id) for d in debts], dtype=float)
    assert not np.allclose(inst.principals, synthetic_wrong)


def test_monthly_income_shorter_than_horizon_raises() -> None:
    debts, profile = _profile_and_debts(principals=(1.0, 2.0), income_len=2)
    with pytest.raises(OptimizationInstanceError, match="monthly_income_vector"):
        build_rios_solis_instance(debts, profile, horizon_months=3, user_id=1)


def test_profile_horizon_mismatch_with_income_vector_raises() -> None:
    debts, profile = _profile_and_debts(principals=(1.0, 2.0), income_len=4)
    profile.horizon_months = 99
    with pytest.raises(OptimizationInstanceError, match="horizon_months"):
        build_rios_solis_instance(debts, profile, horizon_months=3, user_id=1)


def test_source_json_vector_length_mismatch_is_ignored_for_solver_instance() -> None:
    debts, profile = _profile_and_debts(principals=(1.0, 2.0))
    assert profile.source_json is not None
    profile.source_json["principals"] = [1.0]
    inst = build_rios_solis_instance(debts, profile, horizon_months=3, user_id=1)
    np.testing.assert_array_equal(inst.principals, np.array([1.0, 2.0]))


def test_non_canonical_debt_order_raises() -> None:
    """Cars must precede bank loans in id order (Rios-Solis indexing)."""
    debts = [
        DebtORM(
            id=1,
            user_id=1,
            name="b",
            loan_type="bank_loan",
            principal=100.0,
            fixed_payment=1.0,
            min_payment_pct=0.1,
            prepay_penalty=0.0,
            interest_rate_monthly=0.01,
            default_rate_monthly=0.02,
            stipulated_amount=10.0,
            release_time=0,
        ),
        DebtORM(
            id=2,
            user_id=1,
            name="c",
            loan_type="car_loan",
            principal=50.0,
            fixed_payment=2.0,
            min_payment_pct=0.1,
            prepay_penalty=0.0,
            interest_rate_monthly=0.01,
            default_rate_monthly=0.02,
            stipulated_amount=10.0,
            release_time=0,
        ),
    ]
    profile = ScenarioProfileORM(
        user_id=1,
        code="x",
        horizon_months=3,
        monthly_income_vector=[1.0, 1.0, 1.0],
        source_json={
            "principals": [100.0, 50.0],
            "fixedPayment": [1.0, 2.0],
            "minPaymentPct": [0.1, 0.1],
            "prepayPenalty": [0.0, 0.0],
            "stipulatedAmount": [10.0, 10.0],
            "loanTypes": ["bank_loan", "car_loan"],
            "releaseTimeByLoan": [0, 0],
        },
        baseline_reference=None,
    )
    with pytest.raises(OptimizationInstanceError, match="canonical"):
        build_rios_solis_instance(debts, profile, horizon_months=3, user_id=1)


def test_unsupported_loan_type_raises() -> None:
    debts, profile = _profile_and_debts(principals=(10.0, 20.0))
    debts[0].loan_type = "payday"
    with pytest.raises(OptimizationInstanceError, match="Unsupported loan_type"):
        build_rios_solis_instance(debts, profile, horizon_months=3, user_id=1)
