"""Add contracts table for e-sign workflow.

Revision ID: 004
Revises: 003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("html_content", sa.Text, nullable=False),
        sa.Column("contract_amount", sa.Float, nullable=False),
        sa.Column("payment_schedule_json", sa.Text),
        sa.Column("signer_name", sa.String(255)),
        sa.Column("signer_ip", sa.String(45)),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.Column("first_viewed_at", sa.DateTime(timezone=True)),
        sa.Column("view_count", sa.Integer, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("company_phone", sa.String(20)),
        sa.Column("company_license", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # RLS policy
    op.execute("ALTER TABLE contracts ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY contracts_tenant_isolation ON contracts "
        "USING (company_id = current_setting('app.current_company_id', true))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS contracts_tenant_isolation ON contracts")
    op.drop_table("contracts")
