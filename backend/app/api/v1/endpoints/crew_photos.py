"""Crew photo upload endpoints — public (token-based, no auth).

The crew lead gets an SMS link like /crew/{token} that opens a guided
milestone photo upload page. Each project gets a unique crew token.
"""

import logging
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_system_session, get_tenant_session
from app.middleware.tenant import get_company_id
from app.models.project import Project, ProjectMilestone, MilestoneStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["crew-photos"])


# ─── Milestone photo requirements per project type ────────────────

ROOFING_MILESTONES = [
    {
        "name": "Before — Full roof overview",
        "description": "Stand across the street. Get the full roof in one shot.",
        "sort_order": 1,
    },
    {
        "name": "Tear-off complete",
        "description": "Show the exposed decking after old shingles removed. Include any damaged decking.",
        "sort_order": 2,
    },
    {
        "name": "Underlayment installed",
        "description": "Show ice/water shield at eaves and synthetic underlayment on the full roof.",
        "sort_order": 3,
    },
    {
        "name": "Flashing & valleys",
        "description": "Close-up of step flashing, chimney flashing, and valley metal. Show each penetration.",
        "sort_order": 4,
    },
    {
        "name": "Shingles installed",
        "description": "Full roof shot showing completed shingle installation from street level.",
        "sort_order": 5,
    },
    {
        "name": "Ridge cap & vents",
        "description": "Close-up of ridge cap, ridge vent, and any pipe boots or exhaust vents.",
        "sort_order": 6,
    },
    {
        "name": "Cleanup complete",
        "description": "Show the yard, driveway, and landscaping. Prove magnetic nail sweep was done.",
        "sort_order": 7,
    },
    {
        "name": "After — Final overview",
        "description": "Same angle as 'Before' photo. Stand across the street, full roof in shot.",
        "sort_order": 8,
    },
]

SIDING_MILESTONES = [
    {"name": "Before — Full exterior", "description": "Show the full side(s) being sided.", "sort_order": 1},
    {"name": "Old siding removed", "description": "Show exposed sheathing/house wrap.", "sort_order": 2},
    {"name": "House wrap / insulation", "description": "Show house wrap or insulation board installed.", "sort_order": 3},
    {"name": "Siding installed", "description": "Show completed siding on each wall.", "sort_order": 4},
    {"name": "Trim & detail work", "description": "Close-ups of corners, J-channel, window trim.", "sort_order": 5},
    {"name": "After — Final exterior", "description": "Same angle as 'Before'. Full exterior shot.", "sort_order": 6},
]


def _get_milestones_for_type(project_type: str) -> list[dict]:
    if "siding" in project_type:
        return SIDING_MILESTONES
    return ROOFING_MILESTONES


# ─── Authenticated: Generate crew photo link ──────────────────────


@router.post("/projects/{project_id}/crew-photo-link")
async def generate_crew_photo_link(
    project_id: uuid.UUID,
    company_id: str = Depends(get_company_id),
):
    """Generate a crew photo upload link and create milestone records if needed."""
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.milestones))
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Generate token if not set (store in description field for now)
        # In production this should be a dedicated column
        crew_token = secrets.token_urlsafe(16)

        # Create milestones if none exist
        if not project.milestones:
            templates = _get_milestones_for_type(project.project_type.value)
            for tmpl in templates:
                milestone = ProjectMilestone(
                    company_id=company_id,
                    project_id=project.id,
                    name=tmpl["name"],
                    sort_order=tmpl["sort_order"],
                    requires_photo=True,
                    requires_human_signoff=False,
                    notes=tmpl["description"],
                )
                session.add(milestone)

        await session.flush()

        # Get milestone IDs for the response
        result = await session.execute(
            select(ProjectMilestone)
            .where(ProjectMilestone.project_id == project_id)
            .order_by(ProjectMilestone.sort_order)
        )
        milestones = result.scalars().all()

    return {
        "crew_token": crew_token,
        "project_id": str(project_id),
        "milestones": [
            {
                "id": str(m.id),
                "name": m.name,
                "description": m.notes or "",
                "sort_order": m.sort_order,
                "status": m.status.value,
                "has_photo": bool(m.photo_urls),
            }
            for m in milestones
        ],
    }


# ─── Public: Get project milestones by token ─────────────────────


@router.get("/public/crew/{project_id}/milestones")
async def get_crew_milestones(project_id: str):
    """Public: get milestone status and photo requirements for a project."""
    async with get_system_session() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.milestones))
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        milestones = sorted(project.milestones, key=lambda m: m.sort_order)

    return {
        "project_id": str(project.id),
        "property_address": project.property_address,
        "project_type": project.project_type.value,
        "milestones": [
            {
                "id": str(m.id),
                "name": m.name,
                "description": m.notes or "",
                "sort_order": m.sort_order,
                "status": m.status.value,
                "has_photo": bool(m.photo_urls),
                "photo_urls": m.photo_urls.split(",") if m.photo_urls else [],
            }
            for m in milestones
        ],
    }


class UploadPhotoRequest(BaseModel):
    milestone_id: str
    photo_url: str  # For now, URL-based (MMS photos or S3 presigned)


@router.post("/public/crew/{project_id}/upload-photo")
async def upload_milestone_photo(
    project_id: str,
    data: UploadPhotoRequest,
):
    """Public: record a milestone photo upload.

    In production, this would accept file uploads to S3. For now, it
    accepts a photo URL (from MMS or presigned upload).
    """
    from datetime import UTC, datetime

    async with get_system_session() as session:
        result = await session.execute(
            select(ProjectMilestone).where(
                ProjectMilestone.id == data.milestone_id,
                ProjectMilestone.project_id == project_id,
            )
        )
        milestone = result.scalar_one_or_none()
        if not milestone:
            raise HTTPException(status_code=404, detail="Milestone not found")

        # Append photo URL
        existing = milestone.photo_urls or ""
        if existing:
            milestone.photo_urls = existing + "," + data.photo_url
        else:
            milestone.photo_urls = data.photo_url

        milestone.status = MilestoneStatus.AWAITING_QC
        await session.flush()

    return {
        "status": "uploaded",
        "milestone_id": data.milestone_id,
        "milestone_name": milestone.name,
    }


@router.post("/public/crew/{project_id}/complete-milestone")
async def complete_milestone(
    project_id: str,
    data: UploadPhotoRequest,
):
    """Public: mark a milestone as complete with its final photo."""
    from datetime import UTC, datetime

    # First upload the photo
    await upload_milestone_photo(project_id, data)

    async with get_system_session() as session:
        result = await session.execute(
            select(ProjectMilestone).where(
                ProjectMilestone.id == data.milestone_id,
            )
        )
        milestone = result.scalar_one_or_none()
        if milestone:
            milestone.status = MilestoneStatus.AWAITING_QC
            await session.flush()

    return {"status": "milestone_completed", "milestone_id": data.milestone_id}
