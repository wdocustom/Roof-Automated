"""Project completion service — auto-detects when all milestones pass QC.

When the last milestone is approved:
  1. Sets project status to COMPLETED
  2. Generates customer_token (permanent project page link)
  3. Sends final 50% invoice via Stripe
  4. Texts customer the project page link (recap, pay, review, refer)

This is the bridge between QC approval and the Payment & Closure Agent.
"""

import logging
import secrets

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_system_session
from app.models.company import Company
from app.models.project import (
    MilestoneStatus,
    Project,
    ProjectMilestone,
    ProjectStatus,
)

logger = logging.getLogger(__name__)


async def check_project_completion(project_id: str, company_id: str) -> dict:
    """Check if all milestones are approved; if so, complete the project.

    Returns:
        dict with "completed" bool and details about actions taken.
    """
    async with get_system_session() as session:
        result = await session.execute(
            select(Project)
            .options(
                selectinload(Project.milestones),
                selectinload(Project.customer),
            )
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"completed": False, "reason": "project_not_found"}

        milestones = project.milestones or []
        if not milestones:
            return {"completed": False, "reason": "no_milestones"}

        # Check if ALL milestones are approved
        all_approved = all(m.status == MilestoneStatus.APPROVED for m in milestones)
        if not all_approved:
            pending = [m.name for m in milestones if m.status != MilestoneStatus.APPROVED]
            return {
                "completed": False,
                "reason": "milestones_pending",
                "pending": pending,
            }

        # Already completed? Don't re-trigger
        if project.status in (
            ProjectStatus.COMPLETED,
            ProjectStatus.INVOICED,
            ProjectStatus.PAID,
        ):
            return {"completed": True, "reason": "already_completed"}

        # ─── All milestones approved → complete the project ─────────
        from datetime import UTC, datetime

        project.status = ProjectStatus.COMPLETED
        project.actual_end = datetime.now(UTC)

        # Generate customer token if not set
        if not project.customer_token:
            project.customer_token = secrets.token_urlsafe(20)

        customer_token = project.customer_token
        await session.flush()

        # Get company info for SMS
        co_result = await session.execute(
            select(Company).where(Company.clerk_org_id == project.company_id)
        )
        company = co_result.scalar_one_or_none()

        customer_phone = project.customer.phone if project.customer else None
        contract_amount = project.contract_amount or 0
        final_amount = round(contract_amount * 0.5, 2)
        company_name = company.name if company else "Your Contractor"

    logger.info(
        "Project %s completed — all %d milestones approved",
        project_id,
        len(milestones),
    )

    actions_taken = []

    # ─── Send final invoice + customer page link via SMS ────────
    if customer_phone and final_amount > 0:
        try:
            await _send_final_invoice_sms(
                customer_phone=customer_phone,
                company_id=company_id,
                company_name=company_name,
                project_id=str(project_id),
                customer_token=customer_token,
                final_amount=final_amount,
                property_address=project.property_address or "",
                project_type=project.project_type.value if project.project_type else "",
            )
            actions_taken.append("final_invoice_sent")
        except Exception:
            logger.exception("Failed to send final invoice SMS for project %s", project_id)
            actions_taken.append("final_invoice_failed")

    # ─── Emit JOB_COMPLETED event ───────────────────────────────
    try:
        from app.agents.events import Event, EventType, emit_event

        await emit_event(
            company_id=company_id,
            event=Event(
                event_type=EventType.JOB_COMPLETED,
                agent_name="completion_service",
                project_id=str(project_id),
                data={
                    "milestones_completed": len(milestones),
                    "customer_token": customer_token,
                    "final_amount": final_amount,
                },
                description=f"All {len(milestones)} milestones approved — project completed",
            ),
        )
        actions_taken.append("job_completed_event_emitted")
    except Exception:
        logger.exception("Failed to emit JOB_COMPLETED event for project %s", project_id)

    return {
        "completed": True,
        "customer_token": customer_token,
        "final_amount": final_amount,
        "actions": actions_taken,
    }


async def _send_final_invoice_sms(
    *,
    customer_phone: str,
    company_id: str,
    company_name: str,
    project_id: str,
    customer_token: str,
    final_amount: float,
    property_address: str,
    project_type: str,
) -> None:
    """Send the final invoice + project page link to the customer."""
    from app.integrations.stripe.payments import create_payment_link

    # Create Stripe payment link for final 50%
    payment_url = await create_payment_link(
        amount_cents=int(final_amount * 100),
        description=(
            f"Final payment — {project_type.replace('_', ' ').title()} "
            f"at {property_address}"
        ),
        metadata={
            "project_id": project_id,
            "company_id": company_id,
            "payment_type": "final",
        },
    )

    # Build the customer project page URL
    from app.core.config import settings

    frontend_url = getattr(settings, "FRONTEND_URL", "https://roof-automated.vercel.app")
    project_page_url = f"{frontend_url}/my-project/{customer_token}"

    # Send SMS with both links
    from app.agents.tools.messaging import send_text_message

    message = (
        f"Your {project_type.replace('_', ' ')} at {property_address} is complete! "
        f"Great working with you.\n\n"
        f"Final balance: ${final_amount:,.2f}\n"
        f"Pay here: {payment_url}\n\n"
        f"View your project, photos & warranty:\n"
        f"{project_page_url}\n\n"
        f"Thank you for choosing {company_name}!"
    )

    await send_text_message.ainvoke({
        "to_phone": customer_phone,
        "body": message,
        "from_phone": "",  # Will use default
    })

    logger.info(
        "Final invoice SMS sent to %s for project %s ($%.2f)",
        customer_phone,
        project_id,
        final_amount,
    )
