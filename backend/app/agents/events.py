"""Agent Event System — structured events for swarm coordination.

Agents communicate via events, NOT direct shared mutable state. This prevents
race conditions and ensures a clean audit trail. Each event is:
  1. Emitted by an agent
  2. Stored in the database (append-only)
  3. Consumed by the Orchestrator to route next actions
  4. Visible in the dashboard for audit/debugging

Pattern: Event Sourcing. Project state is derived from the event stream.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


# ---------------------------------------------------------------------------
# Event Types
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    # Lead & Onboarding
    LEAD_CREATED = "lead_created"
    LEAD_QUALIFIED = "lead_qualified"
    ESTIMATE_GENERATED = "estimate_generated"
    CONTRACT_SENT = "contract_sent"
    CONTRACT_SIGNED = "contract_signed"

    # Scheduling & Execution
    JOB_SCHEDULED = "job_scheduled"
    JOB_RESCHEDULED = "job_rescheduled"
    WEATHER_ALERT = "weather_alert"
    CREW_DISPATCHED = "crew_dispatched"
    CREW_ARRIVED = "crew_arrived"
    MATERIAL_ORDERED = "material_ordered"
    MATERIAL_DELAYED = "material_delayed"

    # Progress & QC
    MILESTONE_STARTED = "milestone_started"
    MILESTONE_PHOTO_UPLOADED = "milestone_photo_uploaded"
    MILESTONE_QC_PASSED = "milestone_qc_passed"
    MILESTONE_QC_FAILED = "milestone_qc_failed"
    MILESTONE_HUMAN_APPROVAL_REQUESTED = "milestone_human_approval_requested"
    MILESTONE_HUMAN_APPROVED = "milestone_human_approved"
    MILESTONE_HUMAN_REJECTED = "milestone_human_rejected"

    # Payments
    INVOICE_SENT = "invoice_sent"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_REMINDER_SENT = "payment_reminder_sent"
    PAYMENT_OVERDUE = "payment_overdue"

    # Closure
    JOB_COMPLETED = "job_completed"
    WARRANTY_GENERATED = "warranty_generated"

    # System
    HUMAN_ESCALATION = "human_escalation"
    AGENT_ERROR = "agent_error"
    CUSTOMER_MESSAGE = "customer_message"
    CREW_MESSAGE = "crew_message"


# ---------------------------------------------------------------------------
# Event Model (Database)
# ---------------------------------------------------------------------------

class ProjectEvent(Base, TenantMixin):
    """Immutable event in a project's event stream."""

    __tablename__ = "project_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Event Helpers
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """In-memory event before persistence."""

    event_type: EventType
    agent_name: str
    project_id: str
    data: dict = field(default_factory=dict)
    description: str = ""


async def emit_event(company_id: str, event: Event) -> str:
    """Persist an event to the project event stream. Returns event ID."""
    from app.core.database import get_tenant_session

    async with get_tenant_session(company_id) as session:
        db_event = ProjectEvent(
            company_id=company_id,
            project_id=uuid.UUID(event.project_id),
            event_type=event.event_type.value,
            agent_name=event.agent_name,
            data=event.data,
            description=event.description,
        )
        session.add(db_event)
        await session.flush()
        return str(db_event.id)


async def get_project_events(
    company_id: str,
    project_id: str,
    event_types: list[str] | None = None,
    limit: int = 50,
) -> list[dict]:
    """Fetch recent events for a project."""
    from app.core.database import get_tenant_session

    async with get_tenant_session(company_id) as session:
        query = (
            select(ProjectEvent)
            .where(ProjectEvent.project_id == uuid.UUID(project_id))
            .order_by(ProjectEvent.created_at.desc())
            .limit(limit)
        )

        if event_types:
            query = query.where(ProjectEvent.event_type.in_(event_types))

        result = await session.execute(query)
        events = result.scalars().all()

        return [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "agent_name": e.agent_name,
                "data": e.data,
                "description": e.description,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
