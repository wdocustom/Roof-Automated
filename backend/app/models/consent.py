"""TCPA/10DLC SMS consent tracking — legally required for all A2P messaging."""

import enum
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class ConsentStatus(enum.StrEnum):
    OPTED_IN = "opted_in"
    OPTED_OUT = "opted_out"
    PENDING = "pending"


class ConsentSource(enum.StrEnum):
    WEB_FORM = "web_form"
    TEXT_KEYWORD = "text_keyword"  # Customer texted in first
    VERBAL = "verbal"  # Logged by sales rep
    IMPORT = "import"  # From CSV/CRM import
    API = "api"


class SMSConsent(BaseModel, TenantMixin):
    """Record of SMS consent per phone number. Permanent retention (legal requirement)."""

    __tablename__ = "sms_consents"

    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    status: Mapped[ConsentStatus] = mapped_column(Enum(ConsentStatus), nullable=False)
    source: Mapped[ConsentSource] = mapped_column(Enum(ConsentSource), nullable=False)

    # When consent was given/revoked
    consented_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))

    # Evidence
    consent_text: Mapped[str | None] = mapped_column(Text)  # What the customer agreed to
    ip_address: Mapped[str | None] = mapped_column(String(45))
    notes: Mapped[str | None] = mapped_column(Text)
