"""Audit log — every agent action and significant system event is recorded."""

import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class AuditLog(BaseModel, TenantMixin):
    """Immutable log of agent decisions and system actions. Liability protection."""

    __tablename__ = "audit_logs"

    # What happened
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "project", "message"
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Who/what did it
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "agent", "user", "system"
    actor_id: Mapped[str | None] = mapped_column(String(255))
    agent_name: Mapped[str | None] = mapped_column(String(100))

    # Details
    description: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)  # Flexible payload

    # Confidence (for agent actions)
    confidence_score: Mapped[float | None] = mapped_column()
