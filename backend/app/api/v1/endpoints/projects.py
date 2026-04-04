"""Project (job) CRUD endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.database import get_tenant_session
from app.middleware.tenant import get_company_id
from app.models.project import Project, ProjectStatus
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    company_id: str = Depends(get_company_id),
    status_filter: ProjectStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """List projects for the current tenant with optional status filter."""
    try:
        async with get_tenant_session(company_id) as session:
            query = select(Project)
            count_query = select(func.count(Project.id))

            if status_filter:
                query = query.where(Project.status == status_filter)
                count_query = count_query.where(Project.status == status_filter)

            query = query.order_by(Project.created_at.desc()).offset(skip).limit(limit)

            result = await session.execute(query)
            projects = result.scalars().all()

            count_result = await session.execute(count_query)
            total = count_result.scalar_one()

        return ProjectListResponse(
            items=[ProjectResponse.model_validate(p) for p in projects],
            total=total,
        )
    except (ProgrammingError, DBAPIError):
        logger.warning("list_projects: tables not yet created — returning empty list")
        return ProjectListResponse(items=[], total=0)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    company_id: str = Depends(get_company_id),
):
    """Create a new project (job).

    If customer_id is not provided but customer_name/phone/email are,
    the customer (User) record is created automatically.
    """
    from app.models.user import User, UserRole

    try:
        async with get_tenant_session(company_id) as session:
            customer_id = data.customer_id

            # Auto-create customer if needed
            if not customer_id:
                if not data.customer_name:
                    raise HTTPException(
                        status_code=400,
                        detail="Provide either customer_id or customer_name",
                    )

                # Check for existing customer by phone
                if data.customer_phone:
                    result = await session.execute(
                        select(User).where(User.phone == data.customer_phone)
                    )
                    existing = result.scalar_one_or_none()
                    if existing:
                        customer_id = existing.id

                if not customer_id:
                    name_parts = data.customer_name.strip().split(" ", 1)
                    customer = User(
                        company_id=company_id,
                        clerk_user_id=f"manual-{uuid.uuid4().hex[:12]}",
                        first_name=name_parts[0],
                        last_name=name_parts[1] if len(name_parts) > 1 else "",
                        phone=data.customer_phone,
                        email=data.customer_email,
                        role=UserRole.CUSTOMER,
                    )
                    session.add(customer)
                    await session.flush()
                    customer_id = customer.id

            project = Project(
                company_id=company_id,
                customer_id=customer_id,
                property_address=data.property_address,
                property_city=data.property_city,
                property_state=data.property_state,
                property_zip=data.property_zip,
                project_type=data.project_type,
                status=ProjectStatus.LEAD,
                description=data.description,
                lead_source=data.lead_source or "manual",
            )
            session.add(project)
            await session.flush()
            await session.refresh(project)
            return ProjectResponse.model_validate(project)
    except HTTPException:
        raise
    except (ProgrammingError, DBAPIError):
        raise HTTPException(
            status_code=503, detail="Database tables not yet initialized"
        )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    company_id: str = Depends(get_company_id),
):
    """Get a single project by ID."""
    try:
        async with get_tenant_session(company_id) as session:
            result = await session.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            return ProjectResponse.model_validate(project)
    except (ProgrammingError, DBAPIError):
        raise HTTPException(
            status_code=503, detail="Database tables not yet initialized"
        )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    company_id: str = Depends(get_company_id),
):
    """Update project fields."""
    try:
        async with get_tenant_session(company_id) as session:
            result = await session.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            update_data = data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(project, field, value)

            await session.flush()
            await session.refresh(project)
            return ProjectResponse.model_validate(project)
    except (ProgrammingError, DBAPIError):
        raise HTTPException(
            status_code=503, detail="Database tables not yet initialized"
        )
