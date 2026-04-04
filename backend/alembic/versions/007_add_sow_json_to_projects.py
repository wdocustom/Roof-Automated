"""Add sow_json column to projects for AI-generated scope of work.

Revision ID: 007
Revises: 006
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("sow_json", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "sow_json")
