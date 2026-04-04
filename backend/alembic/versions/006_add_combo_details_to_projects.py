"""Add combo_details column to projects.

Revision ID: 006
Revises: 005
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("combo_details", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "combo_details")
