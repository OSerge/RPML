"""initial users and debts tables

Revision ID: 20260323_0001
Revises:
Create Date: 2026-03-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260323_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "debts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_debts_user_id"), "debts", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_debts_user_id"), table_name="debts")
    op.drop_table("debts")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
