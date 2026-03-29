"""Idempotent demo scenario seed from bundled RPML export JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from rpml.data_loader import load_instance
from server.domain.models.loan_type import parse_loan_type
from server.infrastructure.db.models.debt import DebtORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM


class DemoSeedValidationError(ValueError):
    """Invalid seed export JSON (missing keys or inconsistent lengths)."""


PLACEHOLDER_DEFAULT_RATE_MONTHLY = 0.05

_LOAN_INTEREST_CYCLE: tuple[float, ...] = (
    0.02,
    0.008,
    0.025,
    0.012,
    0.015,
    0.011,
)


def placeholder_interest_rates_monthly(n_loans: int) -> list[float]:
    """Distinct monthly rates per loan (export JSON has no rate vectors).

    Zero rates make MILP and greedy baselines collapse to the same total payment sum;
    different rates restore meaningful Avalanche / Snowball / MILP separation in the UI.
    """
    return [float(_LOAN_INTEREST_CYCLE[i % len(_LOAN_INTEREST_CYCLE)]) for i in range(n_loans)]

REQUIRED_ROOT_KEYS = ("instance", "summary")
REQUIRED_INSTANCE_KEYS = (
    "name",
    "nLoans",
    "horizonMonths",
    "monthlyIncome",
    "principals",
    "fixedPayment",
    "minPaymentPct",
    "prepayPenalty",
    "stipulatedAmount",
    "loanTypes",
    "releaseTimeByLoan",
)

_LOAN_LENGTH_KEYS = (
    "principals",
    "fixedPayment",
    "minPaymentPct",
    "prepayPenalty",
    "stipulatedAmount",
    "loanTypes",
    "releaseTimeByLoan",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def default_seed_json_path() -> Path:
    return _repo_root() / "core" / "rpml" / "result_samples" / "Deudas_4_0_0_2_2_120_fijo_fijo_0.json"


def debt_name_prefix_for_scenario(code: str) -> str:
    """Stable prefix for seeded debt rows (used for idempotent replace without SQL LIKE wildcards)."""
    return f"{code}_loan_"


def _bundled_demo_codes() -> set[str]:
    samples_dir = _repo_root() / "core" / "rpml" / "result_samples"
    return {path.stem for path in samples_dir.glob("Deudas_*.json")}


def _legacy_unprefixed_demo_debt_names() -> set[str]:
    return {f"loan_{idx}" for idx in range(12)}


def validate_seed_document(raw: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(raw, dict):
        raise DemoSeedValidationError("Корень JSON должен быть объектом.")

    missing_root = [k for k in REQUIRED_ROOT_KEYS if k not in raw]
    if missing_root:
        raise DemoSeedValidationError(
            f"Отсутствуют обязательные ключи верхнего уровня: {', '.join(missing_root)}."
        )

    instance = raw["instance"]
    summary = raw["summary"]
    if not isinstance(instance, dict):
        raise DemoSeedValidationError("Поле «instance» должно быть объектом.")
    if not isinstance(summary, dict):
        raise DemoSeedValidationError("Поле «summary» должно быть объектом.")

    missing_inst = [k for k in REQUIRED_INSTANCE_KEYS if k not in instance]
    if missing_inst:
        raise DemoSeedValidationError(
            f"В «instance» отсутствуют ключи: {', '.join(missing_inst)}."
        )

    try:
        n_loans = int(instance["nLoans"])
    except (TypeError, ValueError) as e:
        raise DemoSeedValidationError("«instance.nLoans» должно быть целым числом.") from e
    if n_loans < 1:
        raise DemoSeedValidationError("«instance.nLoans» должно быть >= 1.")

    try:
        horizon_months = int(instance["horizonMonths"])
    except (TypeError, ValueError) as e:
        raise DemoSeedValidationError("«instance.horizonMonths» должно быть целым числом.") from e
    if horizon_months < 1:
        raise DemoSeedValidationError("«instance.horizonMonths» должно быть >= 1.")

    monthly_income = instance["monthlyIncome"]
    if not isinstance(monthly_income, list):
        raise DemoSeedValidationError("«instance.monthlyIncome» должно быть массивом.")
    if len(monthly_income) != horizon_months:
        raise DemoSeedValidationError(
            f"Длина «monthlyIncome» ({len(monthly_income)}) не совпадает с "
            f"«horizonMonths» ({horizon_months})."
        )

    for key in _LOAN_LENGTH_KEYS:
        value = instance[key]
        if not isinstance(value, list):
            raise DemoSeedValidationError(f"«instance.{key}» должно быть массивом.")
        if len(value) != n_loans:
            raise DemoSeedValidationError(
                f"Длина «instance.{key}» ({len(value)}) не совпадает с «nLoans» ({n_loans})."
            )

    normalized_loan_types: list[str] = []
    for idx, raw_type in enumerate(instance["loanTypes"]):
        if not isinstance(raw_type, str):
            raise DemoSeedValidationError(f"loanTypes[{idx}] должно быть строкой.")
        try:
            normalized_loan_types.append(parse_loan_type(raw_type).value)
        except ValueError as exc:
            raise DemoSeedValidationError(str(exc)) from None
    instance["loanTypes"] = normalized_loan_types

    return instance, summary


def _extract_constant_rates(matrix: np.ndarray, label: str) -> list[float]:
    out: list[float] = []
    for idx in range(matrix.shape[0]):
        row = np.asarray(matrix[idx], dtype=float)
        if row.size == 0:
            raise DemoSeedValidationError(f"{label}[{idx}] is empty.")
        if not np.allclose(row, row[0]):
            raise DemoSeedValidationError(
                f"{label}[{idx}] must stay constant across the horizon for demo seed."
            )
        out.append(float(row[0]))
    return out


def _resolve_seed_rates(
    json_path: Path,
    *,
    n_loans: int,
) -> tuple[list[float], list[float], str]:
    dat_path = json_path.with_suffix(".dat")
    if not dat_path.is_file():
        return (
            placeholder_interest_rates_monthly(n_loans),
            [PLACEHOLDER_DEFAULT_RATE_MONTHLY] * n_loans,
            "placeholder_per_loan_rates",
        )

    inst = load_instance(dat_path)
    if inst.n != n_loans:
        raise DemoSeedValidationError(
            f"Количество займов в {dat_path.name} ({inst.n}) не совпадает с JSON ({n_loans})."
        )
    if inst.name != json_path.stem:
        raise DemoSeedValidationError(
            f"Имя инстанса в {dat_path.name} ({inst.name}) не совпадает с JSON ({json_path.stem})."
        )
    return (
        _extract_constant_rates(inst.interest_rates, "interest_rates"),
        _extract_constant_rates(inst.default_rates, "default_rates"),
        "source_dat_rates",
    )


def _build_seed_metadata(
    interest_rates: list[float],
    default_rates: list[float],
    strategy: str,
) -> dict[str, Any]:
    return {
        "assumptions": {
            "rates": (
                "Если рядом с JSON есть исходный .dat, демо использует реальные ставки из него; "
                "иначе применяются placeholder-ставки по каждому займу."
            ),
        },
        "ratesApplied": {
            "interestRateMonthlyByLoan": interest_rates,
            "defaultRateMonthlyByLoan": default_rates,
        },
        "strategy": strategy,
    }


def _build_source_json(
    instance: dict[str, Any],
    *,
    interest_rates: list[float],
    default_rates: list[float],
    strategy: str,
) -> dict[str, Any]:
    base = {
        "principals": instance["principals"],
        "fixedPayment": instance["fixedPayment"],
        "minPaymentPct": instance["minPaymentPct"],
        "prepayPenalty": instance["prepayPenalty"],
        "stipulatedAmount": instance["stipulatedAmount"],
        "monthlyIncome": instance["monthlyIncome"],
        "horizonMonths": instance["horizonMonths"],
        "loanTypes": instance["loanTypes"],
        "releaseTimeByLoan": instance["releaseTimeByLoan"],
        "seedMetadata": _build_seed_metadata(interest_rates, default_rates, strategy),
    }
    return base


def _delete_existing_demo_rows(session: Session, user_id: int, keep_code: str) -> None:
    old_codes = _bundled_demo_codes() - {keep_code}
    if old_codes:
        session.execute(
            delete(ScenarioProfileORM).where(
                ScenarioProfileORM.user_id == user_id,
                ScenarioProfileORM.code.in_(sorted(old_codes)),
            )
        )
        for code in old_codes:
            session.execute(
                delete(DebtORM).where(
                    DebtORM.user_id == user_id,
                    DebtORM.name.startswith(debt_name_prefix_for_scenario(code)),
                )
            )

    session.execute(
        delete(DebtORM).where(
            DebtORM.user_id == user_id,
            DebtORM.name.in_(sorted(_legacy_unprefixed_demo_debt_names())),
        )
    )


def seed_demo_scenario(
    session: Session,
    user_id: int,
    *,
    json_path: Path | None = None,
) -> dict[str, Any]:
    path = json_path if json_path is not None else default_seed_json_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    instance, summary = validate_seed_document(raw)

    code: str = str(instance["name"])
    horizon_months: int = int(instance["horizonMonths"])
    monthly_income_vector: list = list(instance["monthlyIncome"])
    n_loans = int(instance["nLoans"])
    interest_by_loan, default_by_loan, rates_strategy = _resolve_seed_rates(
        path,
        n_loans=n_loans,
    )
    source_json = _build_source_json(
        instance,
        interest_rates=interest_by_loan,
        default_rates=default_by_loan,
        strategy=rates_strategy,
    )

    _delete_existing_demo_rows(session, user_id, code)

    profile = session.scalars(
        select(ScenarioProfileORM).where(
            ScenarioProfileORM.user_id == user_id,
            ScenarioProfileORM.code == code,
        )
    ).first()
    if profile is None:
        profile = ScenarioProfileORM(
            user_id=user_id,
            code=code,
            horizon_months=horizon_months,
            monthly_income_vector=monthly_income_vector,
            source_json=source_json,
            baseline_reference=summary,
        )
        session.add(profile)
    else:
        profile.horizon_months = horizon_months
        profile.monthly_income_vector = monthly_income_vector
        profile.source_json = source_json
        profile.baseline_reference = summary

    prefix = debt_name_prefix_for_scenario(code)
    session.execute(
        delete(DebtORM).where(
            DebtORM.user_id == user_id,
            DebtORM.name.startswith(prefix),
        )
    )

    principals: list = instance["principals"]
    fixed_payment: list = instance["fixedPayment"]
    min_pct: list = instance["minPaymentPct"]
    penalty: list = instance["prepayPenalty"]
    stipulated: list = instance["stipulatedAmount"]
    loan_types: list = instance["loanTypes"]
    release_times: list = instance["releaseTimeByLoan"]

    for i in range(n_loans):
        debt = DebtORM(
            user_id=user_id,
            name=f"{prefix}{i}",
            loan_type=str(parse_loan_type(str(loan_types[i])).value),
            principal=float(principals[i]),
            fixed_payment=float(fixed_payment[i]),
            min_payment_pct=float(min_pct[i]),
            prepay_penalty=float(penalty[i]),
            interest_rate_monthly=interest_by_loan[i],
            default_rate_monthly=default_by_loan[i],
            stipulated_amount=float(stipulated[i]),
            release_time=int(release_times[i]),
        )
        session.add(debt)

    session.flush()
    return {"ok": True, "scenario_code": code, "debts_count": n_loans}


def run_cli() -> None:
    import os
    import sys

    from server.infrastructure.db.session import SessionLocal
    from server.infrastructure.repositories.user_repository import UserRepository

    email = os.environ.get("DEMO_EMAIL", "demo@example.com")
    db = SessionLocal()
    try:
        repo = UserRepository(db)
        user = repo.get_by_email(email)
        if user is None:
            print(
                f"demo seed failed: пользователь с email «{email}» не найден. "
                f"Сначала выполните seed-user (или задайте DEMO_EMAIL на существующего пользователя).",
                file=sys.stderr,
            )
            sys.exit(1)
        seed_demo_scenario(db, user.id)
        db.commit()
        print(f"demo seed ok ({email})")
    finally:
        db.close()


if __name__ == "__main__":
    run_cli()
