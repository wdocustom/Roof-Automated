"""Add customer_token to projects and customer_reviews table.

Revision ID: 005
Revises: 004
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add customer_token to projects
    op.add_column(
        "projects",
        sa.Column("customer_token", sa.String(64), unique=True, index=True),
    )

    # Customer reviews table
    op.create_table(
        "customer_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, unique=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("review_text", sa.Text),
        sa.Column("quality_rating", sa.Integer),
        sa.Column("communication_rating", sa.Integer),
        sa.Column("timeliness_rating", sa.Integer),
        sa.Column("cleanup_rating", sa.Integer),
        sa.Column("reviewer_name", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # RLS
    op.execute("ALTER TABLE customer_reviews ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY customer_reviews_tenant_isolation ON customer_reviews "
        "USING (company_id = current_setting('app.current_company_id', true))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS customer_reviews_tenant_isolation ON customer_reviews")
    op.drop_table("customer_reviews")
    op.drop_column("projects", "customer_token")
