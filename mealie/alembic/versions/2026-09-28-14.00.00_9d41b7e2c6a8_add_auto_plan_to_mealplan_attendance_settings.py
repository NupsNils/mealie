"""add auto plan to mealplan attendance settings

Revision ID: 9d41b7e2c6a8
Revises: 7c2e4a91d3b5
Create Date: 2026-09-28 14:00:00.000000

The rolling plan can fill the empty days of the meal plan once a week. The settings hold when
that happens, how far ahead it fills, and how long a dish rests before it comes round again.

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9d41b7e2c6a8"
down_revision: str | None = "7c2e4a91d3b5"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade():
    with op.batch_alter_table("mealplan_attendance_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("auto_plan_enabled", sa.Boolean(), nullable=False, server_default=sa.sql.expression.false())
        )
        batch_op.add_column(sa.Column("auto_plan_weekday", sa.Integer(), nullable=False, server_default="4"))
        batch_op.add_column(sa.Column("auto_plan_days", sa.Integer(), nullable=False, server_default="14"))
        batch_op.add_column(sa.Column("auto_plan_last_run", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("rotation_cooldown_weeks", sa.Integer(), nullable=False, server_default="6"))


def downgrade():
    with op.batch_alter_table("mealplan_attendance_settings", schema=None) as batch_op:
        batch_op.drop_column("rotation_cooldown_weeks")
        batch_op.drop_column("auto_plan_last_run")
        batch_op.drop_column("auto_plan_days")
        batch_op.drop_column("auto_plan_weekday")
        batch_op.drop_column("auto_plan_enabled")
