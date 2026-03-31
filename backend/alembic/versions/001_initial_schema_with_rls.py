"""Initial schema with Row-Level Security for tenant isolation.

Revision ID: 001
Revises: None
Create Date: 2026-03-30

This migration creates all Phase 1 tables and enforces RLS on every
tenant-scoped table. The RLS policy checks:
    company_id = current_setting('app.current_company_id')

The FastAPI middleware sets this session variable from the Clerk JWT org_id
on every request. This is the foundation of our multi-tenant security model.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# All tenant-scoped tables that need RLS
TENANT_TABLES = [
    "users",
    "projects",
    "milestone_templates",
    "project_milestones",
    "messages",
    "message_media",
    "materials",
    "waste_factors",
    "labor_rates",
    "permit_fees",
    "rate_card_versions",
    "sms_consents",
    "audit_logs",
]


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # -----------------------------------------------------------------------
    # Companies (NOT tenant-scoped — this IS the tenant)
    # -----------------------------------------------------------------------
    op.create_table(
        "companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("clerk_org_id", sa.String(255), unique=True, nullable=False),
        sa.Column("ein", sa.String(20)),
        sa.Column("contractor_license_number", sa.String(100)),
        sa.Column("contractor_license_state", sa.String(2)),
        sa.Column("phone", sa.String(20)),
        sa.Column("email", sa.String(255)),
        sa.Column("address", sa.Text),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(2)),
        sa.Column("zip_code", sa.String(10)),
        sa.Column("twilio_phone_number", sa.String(20)),
        sa.Column("twilio_messaging_service_sid", sa.String(50)),
        sa.Column("human_review_threshold_dollars", sa.Float, default=5000.0),
        sa.Column("agent_confidence_threshold", sa.Float, default=0.7),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Users
    # -----------------------------------------------------------------------
    user_role = sa.Enum(
        "owner", "sales_manager", "crew_lead", "crew_member", "customer", name="userrole"
    )
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("clerk_user_id", sa.String(255), unique=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100)),
        sa.Column("last_name", sa.String(100)),
        sa.Column("phone", sa.String(20), index=True),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Rate Card Versions
    # -----------------------------------------------------------------------
    op.create_table(
        "rate_card_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("version_label", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("updated_by_id", UUID(as_uuid=True)),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Materials
    # -----------------------------------------------------------------------
    material_category = sa.Enum(
        "shingles",
        "underlayment",
        "flashing",
        "ridge_vent",
        "ice_water_shield",
        "drip_edge",
        "nails_fasteners",
        "siding_vinyl",
        "siding_fiber_cement",
        "siding_wood",
        "trim",
        "soffit",
        "gutters",
        "other",
        name="materialcategory",
    )
    unit_type = sa.Enum(
        "square",
        "bundle",
        "linear_foot",
        "square_foot",
        "piece",
        "roll",
        "box",
        name="unittype",
    )
    op.create_table(
        "materials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("category", material_category, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("manufacturer", sa.String(255)),
        sa.Column("sku", sa.String(100)),
        sa.Column("unit_type", unit_type, nullable=False),
        sa.Column("unit_cost", sa.Float, nullable=False),
        sa.Column("units_per_square", sa.Float),
        sa.Column("supplier_name", sa.String(255)),
        sa.Column("supplier_part_number", sa.String(100)),
        sa.Column(
            "rate_card_version_id", UUID(as_uuid=True), sa.ForeignKey("rate_card_versions.id")
        ),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Waste Factors
    # -----------------------------------------------------------------------
    roof_complexity = sa.Enum(
        "simple", "moderate", "complex", "very_complex", name="roofcomplexity"
    )
    op.create_table(
        "waste_factors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("material_category", material_category, nullable=False),
        sa.Column("roof_complexity", roof_complexity, nullable=False),
        sa.Column("waste_percentage", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Labor Rates
    # -----------------------------------------------------------------------
    labor_task_type = sa.Enum(
        "tear_off",
        "install_shingles",
        "install_underlayment",
        "install_flashing",
        "install_siding",
        "install_trim",
        "install_gutters",
        "repair_patch",
        "inspection",
        "cleanup",
        "other",
        name="labortasktype",
    )
    labor_rate_unit = sa.Enum(
        "per_square", "per_linear_foot", "per_hour", "flat_rate", name="laborrateunit"
    )
    op.create_table(
        "labor_rates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("task_type", labor_task_type, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("rate_unit", labor_rate_unit, nullable=False),
        sa.Column("base_rate", sa.Float, nullable=False),
        sa.Column("crew_size_standard", sa.Integer, default=3),
        sa.Column("crew_size_adjustment_pct", sa.Float, default=0.0),
        sa.Column("region_adjustment_pct", sa.Float, default=0.0),
        sa.Column("markup_pct", sa.Float, default=0.0),
        sa.Column(
            "rate_card_version_id", UUID(as_uuid=True), sa.ForeignKey("rate_card_versions.id")
        ),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Permit Fees
    # -----------------------------------------------------------------------
    op.create_table(
        "permit_fees",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("zip_code", sa.String(10), index=True),
        sa.Column("city", sa.String(100)),
        sa.Column("county", sa.String(100)),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("permit_type", sa.String(100), nullable=False),
        sa.Column("base_fee", sa.Float, nullable=False),
        sa.Column("per_sqft_fee", sa.Float, default=0.0),
        sa.Column("notes", sa.Text),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Projects
    # -----------------------------------------------------------------------
    project_type = sa.Enum(
        "roof_replacement",
        "roof_repair",
        "siding_install",
        "siding_repair",
        "gutters",
        "combo",
        "other",
        name="projecttype",
    )
    project_status = sa.Enum(
        "lead",
        "onboarded",
        "estimated",
        "contract_sent",
        "contract_signed",
        "scheduled",
        "in_progress",
        "qc_review",
        "completed",
        "invoiced",
        "paid",
        "cancelled",
        name="projectstatus",
    )
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("property_address", sa.Text, nullable=False),
        sa.Column("property_city", sa.String(100), nullable=False),
        sa.Column("property_state", sa.String(2), nullable=False),
        sa.Column("property_zip", sa.String(10), nullable=False),
        sa.Column("property_lat", sa.Float),
        sa.Column("property_lng", sa.Float),
        sa.Column("project_type", project_type, nullable=False),
        sa.Column("status", project_status, default="lead", nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("estimated_sqft", sa.Float),
        sa.Column("estimate_low", sa.Float),
        sa.Column("estimate_high", sa.Float),
        sa.Column("contract_amount", sa.Float),
        sa.Column("scheduled_start", sa.DateTime(timezone=True)),
        sa.Column("scheduled_end", sa.DateTime(timezone=True)),
        sa.Column("actual_start", sa.DateTime(timezone=True)),
        sa.Column("actual_end", sa.DateTime(timezone=True)),
        sa.Column("crew_lead_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("eagleview_report_id", sa.String(100)),
        sa.Column("contract_docusign_envelope_id", sa.String(100)),
        sa.Column("stripe_payment_intent_id", sa.String(100)),
        sa.Column("lead_source", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Milestone Templates
    # -----------------------------------------------------------------------
    op.create_table(
        "milestone_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("requires_photo", sa.Boolean, default=False),
        sa.Column("requires_human_signoff", sa.Boolean, default=False),
        sa.Column("project_type", project_type),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Project Milestones
    # -----------------------------------------------------------------------
    milestone_status = sa.Enum(
        "pending", "in_progress", "awaiting_qc", "approved", "rejected", name="milestonestatus"
    )
    op.create_table(
        "project_milestones",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("milestone_templates.id")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", milestone_status, default="pending"),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("requires_photo", sa.Boolean, default=False),
        sa.Column("requires_human_signoff", sa.Boolean, default=False),
        sa.Column("photo_urls", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("approved_by_id", UUID(as_uuid=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Messages
    # -----------------------------------------------------------------------
    msg_direction = sa.Enum("inbound", "outbound", name="messagedirection")
    msg_channel = sa.Enum("sms", "mms", "rcs", "whatsapp", name="messagechannel")
    msg_sender = sa.Enum("customer", "agent", "crew", "system", "owner", name="messagesendertype")
    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), index=True),
        sa.Column("from_phone", sa.String(20), nullable=False),
        sa.Column("to_phone", sa.String(20), nullable=False),
        sa.Column("direction", msg_direction, nullable=False),
        sa.Column("sender_type", msg_sender, nullable=False),
        sa.Column("sender_id", UUID(as_uuid=True)),
        sa.Column("body", sa.Text),
        sa.Column("channel", msg_channel, default="sms"),
        sa.Column("twilio_message_sid", sa.String(50), unique=True),
        sa.Column("twilio_status", sa.String(30)),
        sa.Column("agent_name", sa.String(100)),
        sa.Column("agent_confidence", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Message Media
    # -----------------------------------------------------------------------
    op.create_table(
        "message_media",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("media_url", sa.Text, nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # SMS Consents (TCPA)
    # -----------------------------------------------------------------------
    consent_status = sa.Enum("opted_in", "opted_out", "pending", name="consentstatus")
    consent_source = sa.Enum(
        "web_form", "text_keyword", "verbal", "import", "api", name="consentsource"
    )
    op.create_table(
        "sms_consents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("phone_number", sa.String(20), nullable=False, index=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("status", consent_status, nullable=False),
        sa.Column("source", consent_source, nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("consent_text", sa.Text),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # Audit Logs
    # -----------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(36), nullable=False, index=True),
        sa.Column("action", sa.String(100), nullable=False, index=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True)),
        sa.Column("actor_type", sa.String(50), nullable=False),
        sa.Column("actor_id", sa.String(255)),
        sa.Column("agent_name", sa.String(100)),
        sa.Column("description", sa.Text),
        sa.Column("metadata_json", JSONB),
        sa.Column("confidence_score", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -----------------------------------------------------------------------
    # ROW-LEVEL SECURITY — the foundation of tenant isolation
    # -----------------------------------------------------------------------
    for table in TENANT_TABLES:
        # Enable RLS on the table
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

        # Force RLS even for table owners (defense in depth)
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        # Policy: rows visible only when company_id matches the session variable
        op.execute(f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            USING (company_id = current_setting('app.current_company_id', true))
            WITH CHECK (company_id = current_setting('app.current_company_id', true))
        """)


def downgrade() -> None:
    # Drop RLS policies first
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    # Drop tables in reverse dependency order
    for table in [
        "audit_logs",
        "sms_consents",
        "message_media",
        "messages",
        "project_milestones",
        "milestone_templates",
        "projects",
        "permit_fees",
        "labor_rates",
        "waste_factors",
        "materials",
        "rate_card_versions",
        "users",
        "companies",
    ]:
        op.drop_table(table)

    # Drop enums
    for enum_name in [
        "consentsource",
        "consentstatus",
        "messagesendertype",
        "messagechannel",
        "messagedirection",
        "milestonestatus",
        "projectstatus",
        "projecttype",
        "laborrateunit",
        "labortasktype",
        "roofcomplexity",
        "unittype",
        "materialcategory",
        "userrole",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
