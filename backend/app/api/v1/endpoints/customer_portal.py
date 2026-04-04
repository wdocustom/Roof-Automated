"""Customer portal endpoints — living project page.

Every project gets a permanent token-based page that evolves with the project:
  - Estimate stage: SOW preview, cost, contractor info
  - Contract stage: Sign contract, view terms
  - Scheduled: Start date, prep instructions
  - In Progress: Live milestone tracker, crew photos
  - Completed: Final photos, pay button, review, referral
  - Paid: Zero balance, warranty, referral

No auth required — accessed via unique customer_token on the project.
"""

import logging
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_system_session, get_tenant_session
from app.middleware.tenant import get_company_id
from app.models.company import Company
from app.models.contract import Contract
from app.models.project import Project, ProjectMilestone, ProjectStatus
from app.models.review import CustomerReview
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["customer-portal"])


# ─── Status helpers ─────────────────────────────────────────────

# Ordered stages for the progress tracker
STAGE_ORDER = [
    "estimated",
    "contract_sent",
    "contract_signed",
    "scheduled",
    "in_progress",
    "completed",
    "paid",
]

STAGE_LABELS = {
    "estimated": "Estimate",
    "contract_sent": "Contract",
    "contract_signed": "Contract Signed",
    "scheduled": "Scheduled",
    "in_progress": "In Progress",
    "completed": "Completed",
    "paid": "Paid",
}


def _build_stage_tracker(status: str) -> list[dict]:
    """Build an ordered list of stages with completion status."""
    # Map some statuses to their closest stage
    status_map = {
        "lead": "estimated",
        "onboarded": "estimated",
        "qc_review": "in_progress",
        "invoiced": "completed",
    }
    mapped = status_map.get(status, status)

    current_idx = -1
    for i, stage in enumerate(STAGE_ORDER):
        if stage == mapped:
            current_idx = i
            break

    return [
        {
            "stage": stage,
            "label": STAGE_LABELS[stage],
            "completed": i <= current_idx,
            "current": stage == mapped,
        }
        for i, stage in enumerate(STAGE_ORDER)
    ]


# ─── Authenticated: generate customer page link ──────────────────


@router.post("/projects/{project_id}/customer-page")
async def generate_customer_page(
    project_id: uuid.UUID,
    company_id: str = Depends(get_company_id),
):
    """Generate (or return existing) customer-facing project page link."""
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if not project.customer_token:
            project.customer_token = secrets.token_urlsafe(20)
            await session.flush()

    return {
        "customer_token": project.customer_token,
        "project_id": str(project_id),
    }


# ─── Public endpoints (no auth — token-based access) ─────────────


@router.get("/public/project/{token}")
async def get_customer_project_page(token: str):
    """Public: get all data for the living customer project page.

    Returns stage-appropriate data — only what's relevant to the
    homeowner at their current project stage.
    """
    async with get_system_session() as session:
        result = await session.execute(
            select(Project)
            .options(
                selectinload(Project.customer),
                selectinload(Project.milestones),
            )
            .where(Project.customer_token == token)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get company info
        co_result = await session.execute(
            select(Company).where(Company.clerk_org_id == project.company_id)
        )
        company = co_result.scalar_one_or_none()

        # Get contract info (latest)
        contract_result = await session.execute(
            select(Contract)
            .where(Contract.project_id == project.id)
            .order_by(Contract.created_at.desc())
            .limit(1)
        )
        contract = contract_result.scalar_one_or_none()

        # Get review
        review_result = await session.execute(
            select(CustomerReview).where(CustomerReview.project_id == project.id)
        )
        review = review_result.scalar_one_or_none()

    status = project.status.value
    customer = project.customer
    customer_name = (
        f"{customer.first_name or ''} {customer.last_name or ''}".strip()
        if customer
        else ""
    )

    # ─── Stage tracker ──────────────────────────────────────────
    stages = _build_stage_tracker(status)

    # ─── Milestones & photos ────────────────────────────────────
    milestones = sorted(project.milestones or [], key=lambda m: m.sort_order)
    milestone_data = []
    photos = []
    for m in milestones:
        milestone_data.append({
            "name": m.name,
            "status": m.status.value,
            "sort_order": m.sort_order,
            "has_photo": bool(m.photo_urls),
        })
        if m.photo_urls:
            for url in m.photo_urls.split(","):
                photos.append({
                    "milestone": m.name,
                    "url": url.strip(),
                    "sort_order": m.sort_order,
                })

    total_milestones = len(milestones) if milestones else 0
    completed_milestones = sum(
        1 for m in milestones if m.status.value in ("approved", "awaiting_qc")
    ) if milestones else 0

    # ─── Payment status ─────────────────────────────────────────
    contract_amount = project.contract_amount or 0
    deposit_amount = round(contract_amount * 0.5, 2)
    final_amount = round(contract_amount * 0.5, 2)

    is_paid = status == "paid"
    is_completed = status in ("completed", "invoiced", "paid")
    is_in_progress = status in ("in_progress", "qc_review")
    has_contract = status not in ("lead", "onboarded", "estimated")
    is_pre_construction = status in ("estimated", "contract_sent")

    balance_due = 0.0
    if is_paid:
        balance_due = 0.0
    elif is_completed:
        balance_due = final_amount
    elif has_contract and not is_pre_construction:
        balance_due = 0.0  # Deposit already paid post-signing
    else:
        balance_due = contract_amount

    # ─── Contract info ──────────────────────────────────────────
    contract_info = None
    if contract:
        contract_info = {
            "id": str(contract.id),
            "status": "signed" if contract.signed_at else "pending",
            "signed_at": contract.signed_at.isoformat() if contract.signed_at else None,
            "sign_url": f"/sign/{contract.token}" if not contract.signed_at else None,
        }

    # ─── Estimate info ──────────────────────────────────────────
    estimate_info = None
    if project.estimate_low or project.estimate_high or project.contract_amount:
        estimate_info = {
            "estimate_low": project.estimate_low,
            "estimate_high": project.estimate_high,
            "contract_amount": contract_amount,
            "sqft": project.estimated_sqft,
        }

    # ─── Schedule info ──────────────────────────────────────────
    schedule_info = None
    if project.scheduled_start:
        schedule_info = {
            "start_date": project.scheduled_start.isoformat() if project.scheduled_start else None,
            "end_date": project.scheduled_end.isoformat() if project.scheduled_end else None,
        }

    # ─── Hero status message ────────────────────────────────────
    status_message = {
        "lead": "We're reviewing your project",
        "onboarded": "We're preparing your estimate",
        "estimated": "Your estimate is ready",
        "contract_sent": "Your contract is ready for signing",
        "contract_signed": "Contract signed — preparing your project",
        "scheduled": "Your project is scheduled",
        "in_progress": "Work is in progress",
        "qc_review": "Quality inspection in progress",
        "completed": "Your project is complete",
        "invoiced": "Your project is complete",
        "paid": "Your project is complete — paid in full",
        "cancelled": "This project has been cancelled",
    }.get(status, "Project in progress")

    # ─── Hero badge ─────────────────────────────────────────────
    status_badge = {
        "estimated": {"text": "Estimate Ready", "color": "blue"},
        "contract_sent": {"text": "Contract Ready", "color": "indigo"},
        "contract_signed": {"text": "Contract Signed", "color": "green"},
        "scheduled": {"text": "Scheduled", "color": "purple"},
        "in_progress": {"text": "In Progress", "color": "orange"},
        "qc_review": {"text": "Quality Review", "color": "yellow"},
        "completed": {"text": "Project Complete", "color": "green"},
        "invoiced": {"text": "Project Complete", "color": "green"},
        "paid": {"text": "Paid in Full", "color": "green"},
    }.get(status, {"text": status.replace("_", " ").title(), "color": "gray"})

    return {
        "token": token,
        "project_id": str(project.id),
        "status": status,
        "status_message": status_message,
        "status_badge": status_badge,
        "stages": stages,

        # Flags
        "is_paid": is_paid,
        "is_completed": is_completed,
        "is_in_progress": is_in_progress,
        "is_pre_construction": is_pre_construction,
        "has_contract": has_contract,
        "show_payment": is_completed and not is_paid,
        "show_review": is_completed or is_paid,
        "show_referral": is_completed or is_paid,
        "show_milestones": is_in_progress or is_completed or is_paid,
        "show_schedule": schedule_info is not None,
        "show_estimate": is_pre_construction and estimate_info is not None,
        "show_contract": contract_info is not None,

        # Company
        "company_name": company.name if company else "",
        "company_phone": company.phone if company else "",
        "company_license": (
            f"{company.contractor_license_state} #{company.contractor_license_number}"
            if company and company.contractor_license_number
            else ""
        ),

        # Customer
        "customer_name": customer_name,

        # Property
        "property_address": project.property_address,
        "property_city": project.property_city,
        "property_state": project.property_state,
        "property_zip": project.property_zip,

        # Project
        "project_type": project.project_type.value.replace("_", " ").title(),
        "description": project.description or "",
        "created_at": project.created_at.isoformat(),
        "completed_at": project.actual_end.isoformat() if project.actual_end else None,

        # Estimate
        "estimate": estimate_info,

        # Contract
        "contract": contract_info,

        # Schedule
        "schedule": schedule_info,

        # Financial
        "contract_amount": contract_amount,
        "deposit_amount": deposit_amount,
        "balance_due": balance_due,

        # Milestones & Photos
        "milestones": milestone_data,
        "milestone_progress": {
            "total": total_milestones,
            "completed": completed_milestones,
            "percentage": round(
                (completed_milestones / total_milestones * 100) if total_milestones > 0 else 0
            ),
        },
        "photos": photos,

        # Review
        "review": {
            "rating": review.rating,
            "review_text": review.review_text,
            "reviewer_name": review.reviewer_name,
            "quality_rating": review.quality_rating,
            "communication_rating": review.communication_rating,
            "timeliness_rating": review.timeliness_rating,
            "cleanup_rating": review.cleanup_rating,
        } if review else None,

        # Referral
        "referral_text": (
            f"I just had my {project.project_type.value.replace('_', ' ')} done by "
            f"{company.name if company else 'my contractor'} and they were great! "
            f"Text them at {company.phone if company else ''} for a free estimate."
        ),
        "referral_phone": company.phone if company else "",
    }


class SubmitReviewRequest(BaseModel):
    rating: int  # 1-5
    review_text: str = ""
    reviewer_name: str = ""
    quality_rating: int | None = None
    communication_rating: int | None = None
    timeliness_rating: int | None = None
    cleanup_rating: int | None = None


@router.post("/public/project/{token}/review")
async def submit_review(token: str, data: SubmitReviewRequest):
    """Public: submit a review for a completed project."""
    if not 1 <= data.rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    async with get_system_session() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.customer))
            .where(Project.customer_token == token)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Check if review already exists
        existing = await session.execute(
            select(CustomerReview).where(CustomerReview.project_id == project.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Review already submitted")

        review = CustomerReview(
            company_id=project.company_id,
            project_id=project.id,
            customer_id=project.customer_id,
            rating=data.rating,
            review_text=data.review_text or None,
            reviewer_name=data.reviewer_name or (
                f"{project.customer.first_name or ''} {project.customer.last_name or ''}".strip()
                if project.customer
                else None
            ),
            quality_rating=data.quality_rating,
            communication_rating=data.communication_rating,
            timeliness_rating=data.timeliness_rating,
            cleanup_rating=data.cleanup_rating,
        )
        session.add(review)
        await session.flush()

    return {"status": "submitted", "rating": data.rating}


@router.post("/public/project/{token}/pay")
async def generate_payment_link(token: str):
    """Public: generate a Stripe payment link for the remaining balance."""
    from app.integrations.stripe.payments import create_payment_link

    async with get_system_session() as session:
        result = await session.execute(
            select(Project).where(Project.customer_token == token)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if project.status == ProjectStatus.PAID:
            raise HTTPException(status_code=400, detail="Project is already paid")

        co_result = await session.execute(
            select(Company).where(Company.clerk_org_id == project.company_id)
        )
        company = co_result.scalar_one_or_none()

    contract_amount = project.contract_amount or 0
    balance = round(contract_amount * 0.5, 2)  # Final 50%

    company_name = company.name if company else "Your Contractor"

    payment_url = await create_payment_link(
        amount_cents=int(balance * 100),
        description=f"Final payment — {project.project_type.value.replace('_', ' ').title()} at {project.property_address}",
        metadata={
            "project_id": str(project.id),
            "company_id": project.company_id,
            "payment_type": "final",
        },
    )

    return {"payment_url": payment_url, "amount": balance}
