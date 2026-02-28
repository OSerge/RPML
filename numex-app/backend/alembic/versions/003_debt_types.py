"""Add debt types and extended fields.

Revision ID: 003
Revises: 002
Create Date: 2026-02-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    debt_type_enum = postgresql.ENUM(
        "credit_card", "mortgage", "consumer_loan", "car_loan", "microloan",
        name="debt_type_enum",
    )
    debt_type_enum.create(op.get_bind(), checkfirst=True)

    payment_type_enum = postgresql.ENUM(
        "annuity", "differentiated", "minimum_percent",
        name="payment_type_enum",
    )
    payment_type_enum.create(op.get_bind(), checkfirst=True)

    prepayment_policy_enum = postgresql.ENUM(
        "allowed", "prohibited", "with_penalty",
        name="prepayment_policy_enum",
    )
    prepayment_policy_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "debts",
        sa.Column(
            "debt_type",
            debt_type_enum,
            nullable=False,
            server_default="consumer_loan",
        ),
    )
    op.add_column(
        "debts",
        sa.Column(
            "payment_type",
            payment_type_enum,
            nullable=False,
            server_default="annuity",
        ),
    )
    op.add_column(
        "debts",
        sa.Column(
            "prepayment_policy",
            prepayment_policy_enum,
            nullable=False,
            server_default="allowed",
        ),
    )
    op.add_column(
        "debts",
        sa.Column("fixed_payment", sa.Numeric(15, 2), nullable=True),
    )
    op.add_column(
        "debts",
        sa.Column("prepayment_penalty_pct", sa.Numeric(6, 4), nullable=True),
    )
    op.add_column(
        "debts",
        sa.Column("credit_limit", sa.Numeric(15, 2), nullable=True),
    )
    op.add_column(
        "debts",
        sa.Column("grace_period_days", sa.Integer(), nullable=True),
    )

    op.alter_column("debts", "term_months", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("debts", "term_months", existing_type=sa.Integer(), nullable=False)

    op.drop_column("debts", "grace_period_days")
    op.drop_column("debts", "credit_limit")
    op.drop_column("debts", "prepayment_penalty_pct")
    op.drop_column("debts", "fixed_payment")
    op.drop_column("debts", "prepayment_policy")
    op.drop_column("debts", "payment_type")
    op.drop_column("debts", "debt_type")

    op.execute("DROP TYPE IF EXISTS prepayment_policy_enum")
    op.execute("DROP TYPE IF EXISTS payment_type_enum")
    op.execute("DROP TYPE IF EXISTS debt_type_enum")
