"""dataset instance optimization flow

Revision ID: 20260413_0005
Revises: 20260401_0004
Create Date: 2026-04-13

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260413_0005"
down_revision: Union[str, Sequence[str], None] = "20260401_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("optimization_tasks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "input_mode",
                sa.String(length=64),
                nullable=False,
                server_default="scenario_snapshot",
            )
        )
        batch_op.add_column(sa.Column("instance_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("mc_config_json", sa.JSON(), nullable=True))

    with op.batch_alter_table("optimization_plans") as batch_op:
        batch_op.add_column(
            sa.Column(
                "horizon_months",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.add_column(sa.Column("instance_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("mc_config_json", sa.JSON(), nullable=True))

    with op.batch_alter_table("optimization_runs") as batch_op:
        batch_op.alter_column("scenario_profile_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("optimization_runs") as batch_op:
        batch_op.alter_column("scenario_profile_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("optimization_plans") as batch_op:
        batch_op.drop_column("mc_config_json")
        batch_op.drop_column("instance_name")
        batch_op.drop_column("horizon_months")

    with op.batch_alter_table("optimization_tasks") as batch_op:
        batch_op.drop_column("mc_config_json")
        batch_op.drop_column("instance_name")
        batch_op.drop_column("input_mode")
