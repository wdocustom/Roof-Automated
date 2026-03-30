"""Company (tenant) model — the top-level entity for multi-tenancy."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Company(BaseModel):
    """A roofing/siding company. All data is scoped to a company via RLS."""

    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    clerk_org_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Business details (needed for 10DLC, contracts, licensing)
    ein: Mapped[str | None] = mapped_column(String(20))
    contractor_license_number: Mapped[str | None] = mapped_column(String(100))
    contractor_license_state: Mapped[str | None] = mapped_column(String(2))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    zip_code: Mapped[str | None] = mapped_column(String(10))

    # Twilio / messaging config
    twilio_phone_number: Mapped[str | None] = mapped_column(String(20))
    twilio_messaging_service_sid: Mapped[str | None] = mapped_column(String(50))

    # Agent config
    human_review_threshold_dollars: Mapped[float] = mapped_column(default=5000.0)
    agent_confidence_threshold: Mapped[float] = mapped_column(default=0.7)

    is_active: Mapped[bool] = mapped_column(default=True)
