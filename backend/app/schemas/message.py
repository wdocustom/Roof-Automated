"""Pydantic schemas for Message API endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.message import MessageChannel, MessageDirection, MessageSenderType


class MessageCreate(BaseModel):
    project_id: uuid.UUID | None = None
    to_phone: str
    body: str
    channel: MessageChannel = MessageChannel.SMS


class MessageResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    from_phone: str
    to_phone: str
    direction: MessageDirection
    sender_type: MessageSenderType
    body: str | None
    channel: MessageChannel
    twilio_message_sid: str | None
    twilio_status: str | None
    agent_name: str | None
    agent_confidence: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TwilioInboundWebhook(BaseModel):
    """Twilio inbound SMS webhook payload (form-encoded, parsed by FastAPI)."""

    MessageSid: str
    From: str
    To: str
    Body: str | None = None
    NumMedia: int = 0
    # Media URLs are dynamic: MediaUrl0, MediaUrl1, etc.
    # Handled separately in the endpoint


class ConversationThread(BaseModel):
    project_id: uuid.UUID | None
    phone_number: str
    messages: list[MessageResponse]
    total: int
