"""optimization modes and monte carlo summary

Revision ID: 20260401_0004
Revises: 20260323_0003
Create Date: 2026-04-01

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260401_0004"
down_revision: Union[str, Sequence[str], None] = "20260323_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("optimization_tasks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "ru_mode",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "mc_income",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    with op.batch_alter_table("optimization_plans") as batch_op:
        batch_op.add_column(
            sa.Column(
                "ru_mode",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "mc_income",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column("mc_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("optimization_plans") as batch_op:
        batch_op.drop_column("mc_summary")
        batch_op.drop_column("mc_income")
        batch_op.drop_column("ru_mode")
    with op.batch_alter_table("optimization_tasks") as batch_op:
        batch_op.drop_column("mc_income")
        batch_op.drop_column("ru_mode")
