"""Scheduling service — crew availability, weather deconfliction, calendar management.

Central coordinator for:
1. Finding available time slots (weather + crew availability)
2. Requesting crew confirmation via SMS
3. Sending reminders
4. Answering schedule queries from crew leads
5. Notifying homeowner when scheduled
"""

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, func, select

from app.core.database import get_tenant_session
from app.integrations.twilio.sms import send_sms
from app.integrations.weather.client import weather_provider
from app.models.company import Company
from app.models.project import Project, ProjectStatus
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


async def find_available_slots(
    company_id: str,
    property_zip: str,
    duration_days: int = 1,
    start_from: date | None = None,
    crew_lead_id: str | None = None,
) -> list[dict]:
    """Find available work slots considering weather and crew schedule.

    Returns a list of date slots sorted by suitability.
    """
    if not start_from:
        start_from = date.today() + timedelta(days=2)  # At least 2 days out

    # Get weather forecast
    forecast = await weather_provider.get_forecast(zip_code=property_zip, days=14)

    workable_days = []
    for day in forecast.days:
        try:
            day_date = date.fromisoformat(day.date[:10])
        except (ValueError, TypeError):
            continue
        if day_date < start_from:
            continue
        if day.is_workable:
            workable_days.append({
                "date": day.date[:10],
                "conditions": day.conditions,
                "temp_high": day.temp_high_f,
                "precip_chance": day.precip_chance,
                "wind_speed": day.wind_speed_mph,
            })

    # Check crew availability — find dates without existing jobs
    if crew_lead_id:
        async with get_tenant_session(company_id) as session:
            result = await session.execute(
                select(Project.scheduled_start, Project.scheduled_end)
                .where(
                    Project.crew_lead_id == crew_lead_id,
                    Project.status.in_([
                        ProjectStatus.SCHEDULED,
                        ProjectStatus.IN_PROGRESS,
                    ]),
                    Project.scheduled_start.isnot(None),
                )
            )
            busy_dates = set()
            for start, end in result.all():
                if start:
                    d = start.date() if hasattr(start, "date") else date.fromisoformat(str(start)[:10])
                    busy_dates.add(d.isoformat())
                    if end:
                        d_end = end.date() if hasattr(end, "date") else date.fromisoformat(str(end)[:10])
                        delta = (d_end - d).days
                        for i in range(delta + 1):
                            busy_dates.add((d + timedelta(days=i)).isoformat())

        workable_days = [d for d in workable_days if d["date"] not in busy_dates]

    # Find consecutive day blocks for multi-day jobs
    if duration_days <= 1:
        return workable_days[:10]

    slots = []
    dates = [d["date"] for d in workable_days]
    for i in range(len(dates) - duration_days + 1):
        block = dates[i : i + duration_days]
        # Check they're consecutive
        consecutive = True
        for j in range(1, len(block)):
            d1 = date.fromisoformat(block[j - 1])
            d2 = date.fromisoformat(block[j])
            if (d2 - d1).days != 1:
                consecutive = False
                break
        if consecutive:
            block_weather = [d for d in workable_days if d["date"] in block]
            slots.append({
                "start_date": block[0],
                "end_date": block[-1],
                "duration_days": duration_days,
                "days": block_weather,
            })

    return slots[:5]


async def request_crew_availability(
    company_id: str,
    project_id: str,
    crew_lead_id: str,
    proposed_date: str,
    property_address: str,
) -> dict:
    """Send SMS to crew lead requesting availability confirmation."""
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(User).where(User.id == crew_lead_id)
        )
        crew_lead = result.scalar_one_or_none()
        if not crew_lead or not crew_lead.phone:
            raise ValueError("Crew lead not found or has no phone number")

        co_result = await session.execute(
            select(Company).where(Company.clerk_org_id == company_id)
        )
        company = co_result.scalar_one_or_none()

    from_phone = company.twilio_phone_number if company else None
    if not from_phone:
        raise ValueError("No Twilio phone configured")

    crew_name = crew_lead.first_name or "Team"
    msg = (
        f"Hey {crew_name}, are you available for a job on {proposed_date}?\n\n"
        f"Location: {property_address}\n\n"
        f"Reply YES to confirm, or suggest a different date."
    )

    sid = await send_sms(to=crew_lead.phone, from_=from_phone, body=msg)

    return {
        "status": "availability_requested",
        "crew_lead_phone": crew_lead.phone,
        "proposed_date": proposed_date,
        "twilio_sid": sid,
    }


async def confirm_crew_schedule(
    company_id: str,
    project_id: str,
    crew_lead_id: str,
    confirmed_date: str,
) -> dict:
    """Confirm the crew schedule — update project and send confirmations."""
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found")

        result = await session.execute(
            select(User).where(User.id == crew_lead_id)
        )
        crew_lead = result.scalar_one_or_none()

        co_result = await session.execute(
            select(Company).where(Company.clerk_org_id == company_id)
        )
        company = co_result.scalar_one_or_none()

        # Update project scheduling
        project.scheduled_start = datetime.fromisoformat(confirmed_date)
        project.crew_lead_id = crew_lead.id if crew_lead else None
        project.status = ProjectStatus.SCHEDULED
        await session.flush()

    from_phone = company.twilio_phone_number if company else None
    crew_name = crew_lead.first_name if crew_lead else "Team"
    crew_phone = crew_lead.phone if crew_lead else None

    # Confirm to crew lead
    if from_phone and crew_phone:
        await send_sms(
            to=crew_phone,
            from_=from_phone,
            body=(
                f"Confirmed! {crew_name}, you're scheduled for "
                f"{project.property_address} on {confirmed_date}.\n\n"
                f"We'll send a reminder the day before with full details. "
                f"Text SCHEDULE anytime to see your upcoming jobs."
            ),
        )

    return {
        "status": "confirmed",
        "project_id": str(project_id),
        "date": confirmed_date,
        "crew_lead": crew_name,
    }


async def notify_customer_scheduled(
    company_id: str,
    project_id: str,
) -> dict:
    """Notify the homeowner that their project has been scheduled."""
    from sqlalchemy.orm import selectinload

    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.customer))
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project or not project.customer:
            raise ValueError("Project or customer not found")

        co_result = await session.execute(
            select(Company).where(Company.clerk_org_id == company_id)
        )
        company = co_result.scalar_one_or_none()

    customer = project.customer
    from_phone = company.twilio_phone_number if company else None
    if not from_phone or not customer.phone:
        return {"status": "skipped", "reason": "no phone"}

    customer_name = customer.first_name or "there"
    sched_date = ""
    if project.scheduled_start:
        sched_date = project.scheduled_start.strftime("%A, %B %d")

    msg = (
        f"Hi {customer_name}! Great news — your {project.project_type.value.replace('_', ' ')} "
        f"project at {project.property_address} is confirmed for {sched_date}.\n\n"
        f"A few things to prepare:\n"
        f"- Please keep pets inside or contained\n"
        f"- Move vehicles clear of the driveway\n"
        f"- Close blinds on windows near the roof line\n"
        f"- Expect work noise starting around 7:30 AM\n\n"
        f"Questions? Just reply to this text. — {company.name if company else 'Your Contractor'}"
    )

    sid = await send_sms(to=customer.phone, from_=from_phone, body=msg)
    return {"status": "sent", "twilio_sid": sid}


async def get_crew_schedule(
    company_id: str,
    crew_lead_id: str | None = None,
    days_ahead: int = 14,
) -> list[dict]:
    """Get the schedule for a crew lead (or all crews) for the next N days."""
    async with get_tenant_session(company_id) as session:
        query = (
            select(Project)
            .where(
                Project.status.in_([
                    ProjectStatus.SCHEDULED,
                    ProjectStatus.IN_PROGRESS,
                ]),
                Project.scheduled_start.isnot(None),
                Project.scheduled_start >= datetime.now(UTC) - timedelta(days=1),
                Project.scheduled_start <= datetime.now(UTC) + timedelta(days=days_ahead),
            )
            .order_by(Project.scheduled_start)
        )

        if crew_lead_id:
            query = query.where(Project.crew_lead_id == crew_lead_id)

        result = await session.execute(query)
        projects = result.scalars().all()

    schedule = []
    for p in projects:
        schedule.append({
            "project_id": str(p.id),
            "property_address": p.property_address,
            "property_city": p.property_city,
            "project_type": p.project_type.value.replace("_", " ").title(),
            "status": p.status.value,
            "scheduled_start": p.scheduled_start.isoformat() if p.scheduled_start else None,
            "scheduled_end": p.scheduled_end.isoformat() if p.scheduled_end else None,
        })

    return schedule


async def send_crew_reminder(
    company_id: str,
    project_id: str,
) -> dict:
    """Send day-before reminder to crew lead with full job details."""
    from sqlalchemy.orm import selectinload

    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.customer))
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project or not project.crew_lead_id:
            return {"status": "skipped", "reason": "no crew lead"}

        result = await session.execute(
            select(User).where(User.id == project.crew_lead_id)
        )
        crew_lead = result.scalar_one_or_none()

        co_result = await session.execute(
            select(Company).where(Company.clerk_org_id == company_id)
        )
        company = co_result.scalar_one_or_none()

    from_phone = company.twilio_phone_number if company else None
    if not from_phone or not crew_lead or not crew_lead.phone:
        return {"status": "skipped"}

    crew_name = crew_lead.first_name or "Team"
    customer = project.customer
    customer_name = (
        f"{customer.first_name or ''} {customer.last_name or ''}".strip()
        if customer
        else "Homeowner"
    )
    customer_phone = customer.phone if customer else "N/A"
    sched_date = ""
    if project.scheduled_start:
        sched_date = project.scheduled_start.strftime("%A %m/%d")

    # Get weather for job day
    weather_line = ""
    try:
        forecast = await weather_provider.get_forecast(
            zip_code=project.property_zip, days=3
        )
        for day in forecast.days:
            if project.scheduled_start and day.date[:10] == str(project.scheduled_start)[:10]:
                weather_line = f"\nWeather: {day.conditions}, High {day.temp_high_f}°F, {day.precip_chance}% rain"
                break
    except Exception:
        pass

    msg = (
        f"Reminder: {crew_name}, you have a job tomorrow ({sched_date}).\n\n"
        f"Address: {project.property_address}, {project.property_city}\n"
        f"Type: {project.project_type.value.replace('_', ' ').title()}\n"
        f"Homeowner: {customer_name} ({customer_phone})"
        f"{weather_line}\n\n"
        f"Reply SCHEDULE to see all upcoming jobs."
    )

    sid = await send_sms(to=crew_lead.phone, from_=from_phone, body=msg)
    return {"status": "sent", "twilio_sid": sid}


async def handle_crew_schedule_query(
    company_id: str,
    crew_phone: str,
    from_phone: str,
    query_text: str,
) -> str:
    """Handle a crew lead texting 'SCHEDULE' or asking about upcoming jobs.

    Returns the response text sent to the crew lead.
    """
    # Find the crew lead by phone
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(User).where(
                User.phone == crew_phone,
                User.role == UserRole.CREW_LEAD,
            )
        )
        crew_lead = result.scalar_one_or_none()

    if not crew_lead:
        # Not a crew lead — might be a customer
        return ""

    schedule = await get_crew_schedule(
        company_id=company_id,
        crew_lead_id=str(crew_lead.id),
        days_ahead=14,
    )

    crew_name = crew_lead.first_name or "Hey"

    if not schedule:
        response = f"{crew_name}, you have no jobs scheduled in the next 2 weeks. Enjoy the downtime!"
    else:
        response = f"{crew_name}, here's your upcoming schedule:\n\n"
        for job in schedule:
            sched = ""
            if job["scheduled_start"]:
                dt = datetime.fromisoformat(job["scheduled_start"])
                sched = dt.strftime("%a %m/%d")
            response += (
                f"- {sched}: {job['project_type']}\n"
                f"  {job['property_address']}, {job['property_city']}\n\n"
            )

    await send_sms(to=crew_phone, from_=from_phone, body=response)
    return response
