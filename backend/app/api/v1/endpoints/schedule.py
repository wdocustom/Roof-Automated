"""Schedule endpoints — crew availability, calendar, and coordination."""

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.tenant import get_company_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule", tags=["schedule"])


class FindSlotsRequest(BaseModel):
    property_zip: str
    duration_days: int = 1
    start_from: str | None = None  # ISO date
    crew_lead_id: str | None = None


@router.post("/find-slots")
async def find_available_slots(
    data: FindSlotsRequest,
    company_id: str = Depends(get_company_id),
):
    """Find available scheduling slots considering weather and crew availability."""
    from app.services.scheduling import find_available_slots as find_slots

    start = None
    if data.start_from:
        start = date.fromisoformat(data.start_from)

    slots = await find_slots(
        company_id=company_id,
        property_zip=data.property_zip,
        duration_days=data.duration_days,
        start_from=start,
        crew_lead_id=data.crew_lead_id,
    )

    return {"slots": slots}


class RequestAvailabilityRequest(BaseModel):
    crew_lead_id: str
    proposed_date: str
    property_address: str


@router.post("/projects/{project_id}/request-crew")
async def request_crew_availability(
    project_id: uuid.UUID,
    data: RequestAvailabilityRequest,
    company_id: str = Depends(get_company_id),
):
    """Send availability request to a crew lead via SMS."""
    from app.services.scheduling import request_crew_availability as req_avail

    try:
        return await req_avail(
            company_id=company_id,
            project_id=str(project_id),
            crew_lead_id=data.crew_lead_id,
            proposed_date=data.proposed_date,
            property_address=data.property_address,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ConfirmScheduleRequest(BaseModel):
    crew_lead_id: str
    confirmed_date: str


@router.post("/projects/{project_id}/confirm")
async def confirm_schedule(
    project_id: uuid.UUID,
    data: ConfirmScheduleRequest,
    company_id: str = Depends(get_company_id),
):
    """Confirm the schedule — updates project, notifies crew and customer."""
    from app.services.scheduling import (
        confirm_crew_schedule,
        notify_customer_scheduled,
    )

    try:
        result = await confirm_crew_schedule(
            company_id=company_id,
            project_id=str(project_id),
            crew_lead_id=data.crew_lead_id,
            confirmed_date=data.confirmed_date,
        )

        # Also notify the customer
        try:
            await notify_customer_scheduled(company_id, str(project_id))
        except Exception:
            logger.warning("Customer notification failed for %s", project_id)

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/calendar")
async def get_calendar(
    crew_lead_id: str | None = None,
    days_ahead: int = 30,
    company_id: str = Depends(get_company_id),
):
    """Get the schedule calendar for the dashboard."""
    from app.services.scheduling import get_crew_schedule

    schedule = await get_crew_schedule(
        company_id=company_id,
        crew_lead_id=crew_lead_id,
        days_ahead=days_ahead,
    )

    return {"schedule": schedule}


@router.post("/projects/{project_id}/send-reminder")
async def send_reminder(
    project_id: uuid.UUID,
    company_id: str = Depends(get_company_id),
):
    """Send day-before reminder to crew lead."""
    from app.services.scheduling import send_crew_reminder

    return await send_crew_reminder(company_id, str(project_id))
