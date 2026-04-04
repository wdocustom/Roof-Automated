"""Contract model — stores generated contracts with signing tokens.

Each contract gets a unique, unguessable token that serves as the
signing URL. No account needed — the customer just taps the SMS link.
Legally binding under ESIGN Act (15 U.S.C. 7001) and UETA.
"""

import enum
import secrets
import uuid

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TenantMixin


class ContractStatus(enum.StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    SIGNED = "signed"
    EXPIRED = "expired"
    VOIDED = "voided"


def _generate_token() -> str:
    """Generate a cryptographically secure 32-char URL-safe token."""
    return secrets.token_urlsafe(24)


class Contract(BaseModel, TenantMixin):
    """A generated contract for a roofing/siding project."""

    __tablename__ = "contracts"

    # Links
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    project = relationship("Project")

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    customer = relationship("User")

    # Signing token — this IS the signing URL
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, default=_generate_token
    )

    # Status
    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, values_callable=lambda x: [e.value for e in x]),
        default=ContractStatus.DRAFT,
        nullable=False,
    )

    # Contract content (HTML)
    html_content: Mapped[str] = mapped_column(Text, nullable=False)

    # Pricing
    contract_amount: Mapped[float] = mapped_column(Float, nullable=False)

    # Payment schedule (JSON string: [{"milestone": "Deposit", "percentage": 50, "amount": 4250}])
    payment_schedule_json: Mapped[str | None] = mapped_column(Text)

    # Signature data
    signer_name: Mapped[str | None] = mapped_column(String(255))
    signer_ip: Mapped[str | None] = mapped_column(String(45))
    signed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))

    # Viewed tracking
    first_viewed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    view_count: Mapped[int] = mapped_column(default=0)

    # Expiration
    expires_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))

    # Company details snapshot (in case company info changes later)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_phone: Mapped[str | None] = mapped_column(String(20))
    company_license: Mapped[str | None] = mapped_column(String(100))
