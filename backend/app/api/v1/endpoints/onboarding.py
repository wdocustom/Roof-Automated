"""Company onboarding endpoints — new signup → company creation → Twilio provisioning."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import get_system_session
from app.middleware.tenant import AuthContext, get_auth_context
from app.models.company import Company

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingRequest(BaseModel):
    company_name: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    contractor_license_number: str | None = None
    contractor_license_state: str | None = None
    # If provided, try to get a number in this area code
    preferred_area_code: str | None = None
    # Skip Twilio provisioning (useful for dev/testing)
    skip_twilio: bool = False


class OnboardingResponse(BaseModel):
    company_id: str
    company_name: str
    twilio_phone_number: str | None
    messaging_service_sid: str | None
    status: str  # "complete" or "complete_no_twilio"


class OnboardingStatus(BaseModel):
    has_company: bool
    company_name: str | None = None
    company_id: str | None = None


@router.get("/status", response_model=OnboardingStatus)
async def check_onboarding_status(
    auth: AuthContext = Depends(get_auth_context),
):
    """Check if the current user already has a company set up."""
    async with get_system_session() as session:
        result = await session.execute(
            select(Company).where(Company.clerk_org_id == auth.org_id)
        )
        company = result.scalar_one_or_none()

    if company:
        return OnboardingStatus(
            has_company=True,
            company_name=company.name,
            company_id=str(company.id),
        )

    return OnboardingStatus(has_company=False)


@router.post("/complete", response_model=OnboardingResponse)
async def complete_onboarding(
    data: OnboardingRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Create the company record and optionally provision a Twilio number.

    This is called once after signup. Idempotent — if the company already
    exists, it returns the existing record.
    """
    # Check if company already exists for this user
    async with get_system_session() as session:
        result = await session.execute(
            select(Company).where(Company.clerk_org_id == auth.org_id)
        )
        existing = result.scalar_one_or_none()

    if existing:
        return OnboardingResponse(
            company_id=str(existing.id),
            company_name=existing.name,
            twilio_phone_number=existing.twilio_phone_number,
            messaging_service_sid=existing.twilio_messaging_service_sid,
            status="complete",
        )

    # Provision Twilio number if not skipped
    twilio_phone = None
    messaging_sid = None

    if not data.skip_twilio:
        try:
            from app.integrations.twilio.provisioning import (
                provision_number_for_company,
            )

            result = await provision_number_for_company(
                company_name=data.company_name,
                area_code=data.preferred_area_code,
                state=data.state,
            )
            twilio_phone = result["phone_number"]
            messaging_sid = result["messaging_service_sid"]
            logger.info(
                "Twilio provisioned for %s: %s", data.company_name, twilio_phone
            )
        except Exception:
            logger.exception("Twilio provisioning failed for %s", data.company_name)
            # Don't block onboarding — they can add a number later in settings

    # Create company record
    async with get_system_session() as session:
        company = Company(
            name=data.company_name,
            clerk_org_id=auth.org_id,
            phone=data.phone,
            email=data.email or auth.email,
            address=data.address,
            city=data.city,
            state=data.state,
            zip_code=data.zip_code,
            contractor_license_number=data.contractor_license_number,
            contractor_license_state=data.contractor_license_state,
            twilio_phone_number=twilio_phone,
            twilio_messaging_service_sid=messaging_sid,
        )
        session.add(company)
        await session.flush()
        company_id = str(company.id)

    # Seed rate card with industry defaults
    try:
        from app.services.seed_rate_card import seed_rate_card

        seed_counts = await seed_rate_card(company_id)
        logger.info(
            "Rate card seeded for %s: %s", data.company_name, seed_counts
        )
    except Exception:
        logger.exception("Rate card seeding failed for %s", data.company_name)

    status = "complete" if twilio_phone else "complete_no_twilio"

    return OnboardingResponse(
        company_id=company_id,
        company_name=data.company_name,
        twilio_phone_number=twilio_phone,
        messaging_service_sid=messaging_sid,
        status=status,
    )
