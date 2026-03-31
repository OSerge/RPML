"""dashboard seed schema: scenario_profiles, optimization_runs, debt columns

Revision ID: 20260323_0003
Revises: 20260323_0002
Create Date: 2026-03-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260323_0003"
down_revision: Union[str, Sequence[str], None] = "20260323_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scenario_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=255), nullable=False),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("monthly_income_vector", sa.JSON(), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=True),
        sa.Column("baseline_reference", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "code", name="uq_scenario_profiles_user_code"),
    )
    op.create_index(op.f("ix_scenario_profiles_user_id"), "scenario_profiles", ["user_id"], unique=False)
    op.create_table(
        "optimization_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scenario_profile_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("baseline_comparison_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["scenario_profile_id"], ["scenario_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_optimization_runs_user_id"), "optimization_runs", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_optimization_runs_scenario_profile_id"),
        "optimization_runs",
        ["scenario_profile_id"],
        unique=False,
    )
    with op.batch_alter_table("debts") as batch_op:
        batch_op.add_column(sa.Column("loan_type", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("principal", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("fixed_payment", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("min_payment_pct", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("prepay_penalty", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("interest_rate_monthly", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("default_rate_monthly", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("stipulated_amount", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("release_time", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("debts") as batch_op:
        batch_op.drop_column("release_time")
        batch_op.drop_column("stipulated_amount")
        batch_op.drop_column("default_rate_monthly")
        batch_op.drop_column("interest_rate_monthly")
        batch_op.drop_column("prepay_penalty")
        batch_op.drop_column("min_payment_pct")
        batch_op.drop_column("fixed_payment")
        batch_op.drop_column("principal")
        batch_op.drop_column("loan_type")
    op.drop_index(op.f("ix_optimization_runs_scenario_profile_id"), table_name="optimization_runs")
    op.drop_index(op.f("ix_optimization_runs_user_id"), table_name="optimization_runs")
    op.drop_table("optimization_runs")
    op.drop_index(op.f("ix_scenario_profiles_user_id"), table_name="scenario_profiles")
    op.drop_table("scenario_profiles")
