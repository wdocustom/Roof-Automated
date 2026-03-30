"""Pydantic schemas for Project API endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.project import ProjectStatus, ProjectType


class ProjectCreate(BaseModel):
    customer_id: uuid.UUID
    property_address: str
    property_city: str
    property_state: str
    property_zip: str
    project_type: ProjectType
    description: str | None = None
    lead_source: str | None = None


class ProjectUpdate(BaseModel):
    status: ProjectStatus | None = None
    description: str | None = None
    estimated_sqft: float | None = None
    estimate_low: float | None = None
    estimate_high: float | None = None
    contract_amount: float | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    crew_lead_id: uuid.UUID | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    company_id: str
    customer_id: uuid.UUID
    property_address: str
    property_city: str
    property_state: str
    property_zip: str
    project_type: ProjectType
    status: ProjectStatus
    description: str | None
    estimated_sqft: float | None
    estimate_low: float | None
    estimate_high: float | None
    contract_amount: float | None
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    crew_lead_id: uuid.UUID | None
    lead_source: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
