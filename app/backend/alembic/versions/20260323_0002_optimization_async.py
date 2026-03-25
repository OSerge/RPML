"""optimization async tasks and plans

Revision ID: 20260323_0002
Revises: 20260323_0001
Create Date: 2026-03-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260323_0002"
down_revision: Union[str, Sequence[str], None] = "20260323_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "optimization_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("total_cost", sa.Float(), nullable=False),
        sa.Column("payments_matrix", sa.JSON(), nullable=False),
        sa.Column("solver_status", sa.String(length=32), nullable=False),
        sa.Column("input_mode", sa.String(length=64), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_optimization_plans_user_id"), "optimization_plans", ["user_id"], unique=False)
    op.create_table(
        "optimization_tasks",
        sa.Column("celery_task_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["optimization_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("celery_task_id"),
    )
    op.create_index(op.f("ix_optimization_tasks_user_id"), "optimization_tasks", ["user_id"], unique=False)
    op.create_index(op.f("ix_optimization_tasks_status"), "optimization_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_optimization_tasks_plan_id"), "optimization_tasks", ["plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_optimization_tasks_plan_id"), table_name="optimization_tasks")
    op.drop_index(op.f("ix_optimization_tasks_status"), table_name="optimization_tasks")
    op.drop_index(op.f("ix_optimization_tasks_user_id"), table_name="optimization_tasks")
    op.drop_table("optimization_tasks")
    op.drop_index(op.f("ix_optimization_plans_user_id"), table_name="optimization_plans")
    op.drop_table("optimization_plans")
