"""Message model — threaded SMS/MMS conversations tied to projects."""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TenantMixin


class MessageDirection(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageChannel(enum.StrEnum):
    SMS = "sms"
    MMS = "mms"
    RCS = "rcs"
    WHATSAPP = "whatsapp"


class MessageSenderType(enum.StrEnum):
    CUSTOMER = "customer"
    AGENT = "agent"  # AI agent
    CREW = "crew"
    SYSTEM = "system"
    OWNER = "owner"


class Message(BaseModel, TenantMixin):
    """A single message in a conversation thread."""

    __tablename__ = "messages"

    # Thread to a project (optional — some messages happen pre-project)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), index=True
    )

    # Participants
    from_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    to_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    sender_type: Mapped[MessageSenderType] = mapped_column(
        Enum(MessageSenderType, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Content
    body: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[MessageChannel] = mapped_column(
        Enum(MessageChannel, values_callable=lambda x: [e.value for e in x]),
        default=MessageChannel.SMS,
    )

    # Twilio tracking
    twilio_message_sid: Mapped[str | None] = mapped_column(String(50), unique=True)
    twilio_status: Mapped[str | None] = mapped_column(String(30))

    # Agent context (which agent sent/processed this)
    agent_name: Mapped[str | None] = mapped_column(String(100))
    agent_confidence: Mapped[float | None] = mapped_column()

    # Media
    media = relationship("MessageMedia", back_populates="message", cascade="all, delete")


class MessageMedia(BaseModel, TenantMixin):
    """Media attachment on a message (photos, documents)."""

    __tablename__ = "message_media"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False
    )
    message = relationship("Message", back_populates="media")

    media_url: Mapped[str] = mapped_column(Text, nullable=False)  # S3 URL
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column()
    original_filename: Mapped[str | None] = mapped_column(String(255))
