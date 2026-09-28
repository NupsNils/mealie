"""add locale to mealplan attendance settings

Revision ID: 7c2e4a91d3b5
Revises: 51f59d2075d9
Create Date: 2026-09-28 12:00:00.000000

Reminder emails and notifications are sent by the hourly scheduler, which has no request to
read a language from. The settings remember the UI language they were last saved in instead.

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7c2e4a91d3b5"
down_revision: str | None = "51f59d2075d9"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade():
    with op.batch_alter_table("mealplan_attendance_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("locale", sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table("mealplan_attendance_settings", schema=None) as batch_op:
        batch_op.drop_column("locale")
