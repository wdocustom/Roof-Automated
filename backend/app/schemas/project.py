"""Pydantic schemas for Project API endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.project import ProjectStatus, ProjectType


class ProjectCreate(BaseModel):
    # Either provide an existing customer_id, or provide contact info to create one
    customer_id: uuid.UUID | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None

    property_address: str
    property_city: str
    property_state: str
    property_zip: str
    project_type: ProjectType
    combo_details: list[str] | None = None  # ["roof_replacement", "gutters", "siding_install"]
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


class CustomerInfo(BaseModel):
    id: uuid.UUID
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None

    model_config = {"from_attributes": True}


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
    combo_details: str | None = None
    sow_json: str | None = None
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
    customer: CustomerInfo | None = None

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
