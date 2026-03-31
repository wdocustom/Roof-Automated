"""Pydantic schemas for Company Settings API endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class CompanySettingsResponse(BaseModel):
    id: uuid.UUID
    name: str
    phone: str | None
    email: str | None
    address: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    twilio_phone_number: str | None
    human_review_threshold_dollars: float
    agent_confidence_threshold: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanySettingsUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    twilio_phone_number: str | None = None
    human_review_threshold_dollars: float | None = None
    agent_confidence_threshold: float | None = None
