"""LLM context serializer for debt and optimization plan data."""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.models.debt import Debt, DebtType, PaymentType, PrepaymentPolicy
from app.schemas.debt import DEBT_TYPE_LABELS


DEBT_TYPE_RU = {
    DebtType.CREDIT_CARD: "Кредитная карта",
    DebtType.MORTGAGE: "Ипотека",
    DebtType.CONSUMER_LOAN: "Потребительский кредит",
    DebtType.CAR_LOAN: "Автокредит",
    DebtType.MICROLOAN: "Микрозайм",
}

PAYMENT_TYPE_RU = {
    PaymentType.ANNUITY: "аннуитетный",
    PaymentType.DIFFERENTIATED: "дифференцированный",
    PaymentType.MINIMUM_PERCENT: "% от остатка",
}

PREPAYMENT_RU = {
    PrepaymentPolicy.ALLOWED: "разрешено",
    PrepaymentPolicy.PROHIBITED: "запрещено",
    PrepaymentPolicy.WITH_PENALTY: "со штрафом",
}


def format_currency(value: float) -> str:
    """Format number as currency string."""
    return f"{value:,.0f}".replace(",", " ")


def serialize_debt_for_llm(debt: Debt) -> str:
    """Serialize single debt to human-readable text for LLM context."""
    lines = [
        f"- {debt.name} ({DEBT_TYPE_RU.get(debt.debt_type, str(debt.debt_type))})",
        f"  Остаток: {format_currency(float(debt.current_balance))} руб.",
        f"  Ставка: {float(debt.interest_rate_annual):.1f}% годовых",
    ]

    if debt.payment_type == PaymentType.MINIMUM_PERCENT:
        lines.append(f"  Мин. платёж: {float(debt.min_payment_pct):.1f}% от остатка")
    elif debt.fixed_payment:
        lines.append(f"  Платёж: {format_currency(float(debt.fixed_payment))} руб./мес.")

    if debt.term_months:
        lines.append(f"  Срок: {debt.term_months} мес.")

    lines.append(f"  Досрочное погашение: {PREPAYMENT_RU.get(debt.prepayment_policy, 'н/д')}")

    if debt.debt_type == DebtType.CREDIT_CARD:
        if debt.credit_limit:
            lines.append(f"  Лимит: {format_currency(float(debt.credit_limit))} руб.")
        if debt.grace_period_days:
            lines.append(f"  Льготный период: {debt.grace_period_days} дней")

    return "\n".join(lines)


def serialize_debts_for_llm(debts: list[Debt]) -> str:
    """Serialize all user debts to text for LLM context."""
    if not debts:
        return "У пользователя нет долгов."

    total_debt = sum(float(d.current_balance) for d in debts)
    lines = [
        f"Всего долгов: {len(debts)}, общая сумма: {format_currency(total_debt)} руб.",
        "",
    ]

    for debt in sorted(debts, key=lambda d: -float(d.current_balance)):
        lines.append(serialize_debt_for_llm(debt))
        lines.append("")

    return "\n".join(lines)


def serialize_optimization_plan_for_llm(
    plan_data: dict,
    debts: list[Debt],
) -> str:
    """Serialize optimization plan to text for LLM context."""
    lines = []

    total_cost = plan_data.get("total_cost", 0)
    savings = plan_data.get("savings_vs_minimum")
    baseline = plan_data.get("baseline_cost")
    horizon = plan_data.get("horizon_months", 24)
    status = plan_data.get("status", "unknown")

    lines.append(f"Горизонт планирования: {horizon} месяцев")
    lines.append(f"Статус оптимизации: {status}")
    lines.append(f"Общая стоимость по оптимальному плану: {format_currency(total_cost)} руб.")

    if baseline:
        lines.append(f"Стоимость при минимальных платежах: {format_currency(baseline)} руб.")

    if savings and savings > 0:
        lines.append(f"Экономия: {format_currency(savings)} руб.")

    lines.append("")

    payments_matrix = plan_data.get("payments_matrix", {})
    balances_matrix = plan_data.get("balances_matrix", {})

    if payments_matrix:
        lines.append("План платежей по месяцам:")
        debt_map = {d.name: d for d in debts}

        for debt_name, payments in payments_matrix.items():
            debt = debt_map.get(debt_name)
            debt_type = DEBT_TYPE_RU.get(debt.debt_type, "") if debt else ""

            non_zero_payments = [(i + 1, p) for i, p in enumerate(payments) if p > 0.01]

            if non_zero_payments:
                lines.append(f"\n{debt_name} ({debt_type}):")
                total_paid = sum(p for _, p in non_zero_payments)
                last_month = non_zero_payments[-1][0] if non_zero_payments else 0
                lines.append(f"  Всего платежей: {format_currency(total_paid)} руб. за {last_month} мес.")

                if len(non_zero_payments) <= 6:
                    for month, payment in non_zero_payments:
                        lines.append(f"  Месяц {month}: {format_currency(payment)} руб.")
                else:
                    for month, payment in non_zero_payments[:3]:
                        lines.append(f"  Месяц {month}: {format_currency(payment)} руб.")
                    lines.append("  ...")
                    for month, payment in non_zero_payments[-2:]:
                        lines.append(f"  Месяц {month}: {format_currency(payment)} руб.")

    return "\n".join(lines)


def build_llm_context(
    debts: list[Debt],
    plan_data: Optional[dict] = None,
    user_budget: Optional[float] = None,
) -> str:
    """Build complete context string for LLM."""
    sections = []

    sections.append("=== ДОЛГИ ПОЛЬЗОВАТЕЛЯ ===")
    sections.append(serialize_debts_for_llm(debts))

    if user_budget:
        sections.append(f"Месячный бюджет на погашение: {format_currency(user_budget)} руб.")
        sections.append("")

    if plan_data:
        sections.append("=== ПЛАН ОПТИМИЗАЦИИ ===")
        sections.append(serialize_optimization_plan_for_llm(plan_data, debts))

    return "\n".join(sections)
