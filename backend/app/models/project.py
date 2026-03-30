"""Project (job) model with status pipeline and configurable milestones."""

import enum
import uuid

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TenantMixin


class ProjectStatus(str, enum.Enum):
    LEAD = "lead"
    ONBOARDED = "onboarded"
    ESTIMATED = "estimated"
    CONTRACT_SENT = "contract_sent"
    CONTRACT_SIGNED = "contract_signed"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    QC_REVIEW = "qc_review"
    COMPLETED = "completed"
    INVOICED = "invoiced"
    PAID = "paid"
    CANCELLED = "cancelled"


class ProjectType(str, enum.Enum):
    ROOF_REPLACEMENT = "roof_replacement"
    ROOF_REPAIR = "roof_repair"
    SIDING_INSTALL = "siding_install"
    SIDING_REPAIR = "siding_repair"
    GUTTERS = "gutters"
    COMBO = "combo"
    OTHER = "other"


class Project(BaseModel, TenantMixin):
    """A roofing/siding job — the central entity in the lifecycle."""

    __tablename__ = "projects"

    # Customer
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    customer = relationship("User", foreign_keys=[customer_id])

    # Property
    property_address: Mapped[str] = mapped_column(Text, nullable=False)
    property_city: Mapped[str] = mapped_column(String(100), nullable=False)
    property_state: Mapped[str] = mapped_column(String(2), nullable=False)
    property_zip: Mapped[str] = mapped_column(String(10), nullable=False)
    property_lat: Mapped[float | None] = mapped_column(Float)
    property_lng: Mapped[float | None] = mapped_column(Float)

    # Job details
    project_type: Mapped[ProjectType] = mapped_column(Enum(ProjectType), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.LEAD, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)

    # Estimate & pricing
    estimated_sqft: Mapped[float | None] = mapped_column(Float)
    estimate_low: Mapped[float | None] = mapped_column(Float)
    estimate_high: Mapped[float | None] = mapped_column(Float)
    contract_amount: Mapped[float | None] = mapped_column(Float)

    # Scheduling
    scheduled_start: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[str | None] = mapped_column(DateTime(timezone=True))

    # Crew assignment
    crew_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    crew_lead = relationship("User", foreign_keys=[crew_lead_id])

    # External references
    eagleview_report_id: Mapped[str | None] = mapped_column(String(100))
    contract_docusign_envelope_id: Mapped[str | None] = mapped_column(String(100))
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(100))

    # Source tracking
    lead_source: Mapped[str | None] = mapped_column(String(100))

    # Relationships
    milestones = relationship("ProjectMilestone", back_populates="project", cascade="all, delete")


class MilestoneTemplate(BaseModel, TenantMixin):
    """Company-configurable milestone definitions."""

    __tablename__ = "milestone_templates"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    requires_photo: Mapped[bool] = mapped_column(default=False)
    requires_human_signoff: Mapped[bool] = mapped_column(default=False)
    project_type: Mapped[ProjectType | None] = mapped_column(Enum(ProjectType))


class MilestoneStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_QC = "awaiting_qc"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProjectMilestone(BaseModel, TenantMixin):
    """A milestone instance for a specific project."""

    __tablename__ = "project_milestones"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    project = relationship("Project", back_populates="milestones")

    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("milestone_templates.id")
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[MilestoneStatus] = mapped_column(
        Enum(MilestoneStatus), default=MilestoneStatus.PENDING
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    requires_photo: Mapped[bool] = mapped_column(default=False)
    requires_human_signoff: Mapped[bool] = mapped_column(default=False)

    # Evidence
    photo_urls: Mapped[str | None] = mapped_column(Text)  # JSON array of S3 URLs
    notes: Mapped[str | None] = mapped_column(Text)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
