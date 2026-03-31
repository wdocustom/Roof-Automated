"""Add project events table for agent event sourcing.

Revision ID: 003
Revises: 002
Create Date: 2026-03-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("event_type", sa.String(100), nullable=False, index=True),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("data", JSONB),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Composite index for common query pattern
    op.create_index(
        "ix_project_events_project_type",
        "project_events",
        ["project_id", "event_type"],
    )

    # RLS
    op.execute("ALTER TABLE project_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_events FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON project_events
        USING (company_id = current_setting('app.current_company_id', true))
        WITH CHECK (company_id = current_setting('app.current_company_id', true))
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON project_events")
    op.execute("ALTER TABLE project_events DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_project_events_project_type")
    op.drop_table("project_events")
