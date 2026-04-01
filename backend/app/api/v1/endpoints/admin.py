"""Admin endpoints — for platform setup and diagnostics.

These endpoints are for the platform operator (you) to manage companies,
check system health, and bootstrap initial data. In production these
should be protected by an admin auth check.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_system_session
from app.models.company import Company

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class CompanyCreate(BaseModel):
    name: str
    clerk_org_id: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    twilio_phone_number: str | None = None
    twilio_messaging_service_sid: str | None = None


class CompanyUpdate(BaseModel):
    twilio_phone_number: str | None = None
    twilio_messaging_service_sid: str | None = None
    phone: str | None = None
    email: str | None = None
    name: str | None = None


@router.get("/companies")
async def list_companies():
    """List all companies (system-level, no RLS)."""
    async with get_system_session() as session:
        result = await session.execute(select(Company))
        companies = result.scalars().all()
        return [
            {
                "id": str(c.id),
                "name": c.name,
                "clerk_org_id": c.clerk_org_id,
                "phone": c.phone,
                "twilio_phone_number": c.twilio_phone_number,
                "twilio_messaging_service_sid": c.twilio_messaging_service_sid,
                "is_active": c.is_active,
            }
            for c in companies
        ]


@router.post("/companies")
async def create_company(data: CompanyCreate):
    """Create a new company record."""
    async with get_system_session() as session:
        # Check if company already exists
        result = await session.execute(
            select(Company).where(Company.clerk_org_id == data.clerk_org_id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Company already exists")

        company = Company(**data.model_dump(exclude_unset=True))
        session.add(company)
        await session.flush()
        return {
            "id": str(company.id),
            "name": company.name,
            "clerk_org_id": company.clerk_org_id,
        }


@router.patch("/companies/{company_id}")
async def update_company(company_id: str, data: CompanyUpdate):
    """Update a company's config (by UUID id)."""
    async with get_system_session() as session:
        result = await session.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        for key, value in data.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(company, key, value)

        await session.flush()
        return {
            "id": str(company.id),
            "name": company.name,
            "twilio_phone_number": company.twilio_phone_number,
            "twilio_messaging_service_sid": company.twilio_messaging_service_sid,
        }
