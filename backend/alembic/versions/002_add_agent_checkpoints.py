"""Add agent checkpoints table for LangGraph state persistence.

Revision ID: 002
Revises: 001
Create Date: 2026-03-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_checkpoints",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("thread_id", sa.String(255), nullable=False, index=True),
        sa.Column("parent_id", sa.String(255), nullable=True),
        sa.Column("checkpoint_data", JSONB, nullable=False),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # RLS for tenant isolation
    op.execute("ALTER TABLE agent_checkpoints ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_checkpoints FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON agent_checkpoints
        USING (company_id = current_setting('app.current_company_id', true))
        WITH CHECK (company_id = current_setting('app.current_company_id', true))
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON agent_checkpoints")
    op.execute("ALTER TABLE agent_checkpoints DISABLE ROW LEVEL SECURITY")
    op.drop_table("agent_checkpoints")
