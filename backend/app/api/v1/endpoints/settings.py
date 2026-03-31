"""Company settings endpoints — view and update company configuration."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.database import get_tenant_session
from app.middleware.tenant import get_company_id
from app.models.company import Company
from app.schemas.company import CompanySettingsResponse, CompanySettingsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/company", response_model=CompanySettingsResponse)
async def get_company_settings(
    company_id: str = Depends(get_company_id),
):
    """Get current company settings."""
    try:
        async with get_tenant_session(company_id) as session:
            result = await session.execute(
                select(Company).where(Company.clerk_org_id == company_id)
            )
            company = result.scalar_one_or_none()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
            return CompanySettingsResponse.model_validate(company)
    except (ProgrammingError, DBAPIError, HTTPException):
        logger.warning("get_company_settings: tables not yet created — returning defaults")
        return CompanySettingsResponse(
            id="00000000-0000-0000-0000-000000000000",
            name="",
            phone=None,
            email=None,
            address=None,
            city=None,
            state=None,
            zip_code=None,
            twilio_phone_number=None,
            human_review_threshold_dollars=5000.0,
            agent_confidence_threshold=0.7,
            created_at="1970-01-01T00:00:00Z",
            updated_at="1970-01-01T00:00:00Z",
        )


@router.patch("/company", response_model=CompanySettingsResponse)
async def update_company_settings(
    data: CompanySettingsUpdate,
    company_id: str = Depends(get_company_id),
):
    """Update company settings."""
    try:
        async with get_tenant_session(company_id) as session:
            result = await session.execute(
                select(Company).where(Company.clerk_org_id == company_id)
            )
            company = result.scalar_one_or_none()
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            update_data = data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(company, field, value)

            await session.flush()
            await session.refresh(company)
            return CompanySettingsResponse.model_validate(company)
    except (ProgrammingError, DBAPIError):
        raise HTTPException(
            status_code=503, detail="Database tables not yet initialized"
        )
