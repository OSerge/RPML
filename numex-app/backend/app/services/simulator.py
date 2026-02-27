"""Open Banking simulator - synthetic financial data generation."""

import random
from datetime import date, timedelta

from app.models.debt import Debt
from app.models.transaction import Transaction


class UserProfile:
    def __init__(
        self,
        monthly_income: float = 80000,
        income_variance: float = 0.1,
        expense_categories: dict[str, float] | None = None,
    ):
        self.monthly_income = monthly_income
        self.income_variance = income_variance
        self.expense_categories = expense_categories or {
            "food": 15000,
            "transport": 5000,
            "utilities": 8000,
            "entertainment": 5000,
            "other": 7000,
        }


class OpenBankingSimulator:
    """Generate synthetic financial data for development and testing."""

    def __init__(self, profile: UserProfile | None = None):
        self.profile = profile or UserProfile()

    def generate_transactions(
        self,
        user_id,
        months: int = 6,
        start_date: date | None = None,
    ) -> list[Transaction]:
        """Generate synthetic transactions for the given period."""
        start = start_date or date.today().replace(day=1) - timedelta(days=30 * months)
        transactions = []

        for m in range(months):
            month_start = start + timedelta(days=30 * m)
            salary_date = month_start + timedelta(days=random.randint(0, 2))
            salary = self.profile.monthly_income * (1 + random.uniform(-self.profile.income_variance, self.profile.income_variance))
            transactions.append(
                Transaction(
                    user_id=user_id,
                    amount=salary,
                    category="income",
                    date=salary_date,
                    description="Зарплата",
                )
            )

            for category, base_amount in self.profile.expense_categories.items():
                amount = base_amount * random.uniform(0.8, 1.2)
                txn_date = month_start + timedelta(days=random.randint(1, 28))
                transactions.append(
                    Transaction(
                        user_id=user_id,
                        amount=-amount,
                        category=category,
                        date=txn_date,
                        description=f"Расход: {category}",
                    )
                )

        return transactions

    def generate_loans(
        self,
        user_id,
        count: int = 2,
    ) -> list[Debt]:
        """Generate synthetic loan data."""
        loans = []
        templates = [
            {"name": "Кредитная карта Сбербанк", "rate": 24.9, "min_pct": 5, "balance": 150000},
            {"name": "Потребительский кредит", "rate": 18.5, "min_pct": 3, "balance": 300000},
            {"name": "Кредитная карта Тинькофф", "rate": 29.9, "min_pct": 5, "balance": 80000},
        ]

        for i in range(min(count, len(templates))):
            t = templates[i]
            loans.append(
                Debt(
                    user_id=user_id,
                    name=t["name"],
                    principal=t["balance"],
                    current_balance=t["balance"],
                    interest_rate_annual=t["rate"],
                    min_payment_pct=t["min_pct"],
                    late_fee_rate=0.5,
                    start_date=date.today() - timedelta(days=random.randint(90, 365)),
                    term_months=36,
                )
            )
        return loans
