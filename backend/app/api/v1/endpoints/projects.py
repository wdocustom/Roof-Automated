"""Project (job) CRUD endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import selectinload

from app.core.database import get_tenant_session
from app.middleware.tenant import get_company_id
from app.models.project import Project, ProjectStatus, ProjectType
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
            query = select(Project).options(selectinload(Project.customer))
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

            # Auto-detect combo if multiple services selected
            import json

            project_type = data.project_type
            combo_json = None
            if data.combo_details and len(data.combo_details) > 1:
                project_type = ProjectType.COMBO
                combo_json = json.dumps(data.combo_details)
            elif data.combo_details and len(data.combo_details) == 1:
                # Single service selected — use it directly
                try:
                    project_type = ProjectType(data.combo_details[0])
                except ValueError:
                    pass
                combo_json = json.dumps(data.combo_details)

            project = Project(
                company_id=company_id,
                customer_id=customer_id,
                property_address=data.property_address,
                property_city=data.property_city,
                property_state=data.property_state,
                property_zip=data.property_zip,
                project_type=project_type,
                status=ProjectStatus.LEAD,
                description=data.description,
                combo_details=combo_json,
                lead_source=data.lead_source or "manual",
            )
            session.add(project)
            await session.flush()

            # Reload with customer relationship
            result = await session.execute(
                select(Project)
                .options(selectinload(Project.customer))
                .where(Project.id == project.id)
            )
            project = result.scalar_one()
            return ProjectResponse.model_validate(project)
    except HTTPException:
        raise
    except (ProgrammingError, DBAPIError):
        raise HTTPException(
            status_code=503, detail="Database tables not yet initialized"
        )


@router.post("/seed", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def seed_project(
    company_id: str = Depends(get_company_id),
):
    """Seed a demo project with realistic data for testing."""
    import json

    from app.models.user import User, UserRole

    async with get_tenant_session(company_id) as session:
        # Create demo customer
        customer = User(
            company_id=company_id,
            clerk_user_id=f"seed-{uuid.uuid4().hex[:12]}",
            first_name="Sarah",
            last_name="Johnson",
            phone="+14025551234",
            email="sarah.johnson@example.com",
            role=UserRole.CUSTOMER,
        )
        session.add(customer)
        await session.flush()

        project = Project(
            company_id=company_id,
            customer_id=customer.id,
            property_address="4521 Maple Ridge Dr",
            property_city="Omaha",
            property_state="NE",
            property_zip="68114",
            project_type=ProjectType.COMBO,
            status=ProjectStatus.ESTIMATED,
            description=(
                "Full roof replacement (architectural shingles, GAF Timberline HDZ in Charcoal) "
                "and seamless aluminum gutter install (5-inch K-style, white). "
                "Existing 3-tab shingles showing granule loss and curling on south-facing slope. "
                "Gutters have multiple sag points and downspout disconnections. "
                "2,400 sq ft roof, 180 linear ft gutters."
            ),
            combo_details=json.dumps(["roof_replacement", "gutters"]),
            estimated_sqft=2400.0,
            estimate_low=12800.0,
            estimate_high=15200.0,
            contract_amount=14000.0,
            lead_source="seed",
        )
        session.add(project)
        await session.flush()

        # Reload with customer relationship
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.customer))
            .where(Project.id == project.id)
        )
        project = result.scalar_one()
        return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    company_id: str = Depends(get_company_id),
):
    """Get a single project by ID."""
    try:
        async with get_tenant_session(company_id) as session:
            result = await session.execute(
                select(Project)
                .options(selectinload(Project.customer))
                .where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            return ProjectResponse.model_validate(project)
    except (ProgrammingError, DBAPIError):
        raise HTTPException(
            status_code=503, detail="Database tables not yet initialized"
        )


@router.post("/{project_id}/send-invoice")
async def send_invoice(
    project_id: uuid.UUID,
    company_id: str = Depends(get_company_id),
):
    """Generate a Stripe payment link and send it to the customer via SMS.

    Uses the project's contract_amount. Falls back to estimate_high if no contract.
    """
    from app.integrations.stripe.payments import create_payment_link
    from app.integrations.twilio.sms import send_sms
    from app.models.company import Company
    from app.models.user import User

    try:
        async with get_tenant_session(company_id) as session:
            result = await session.execute(
                select(Project)
                .options(selectinload(Project.customer))
                .where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            amount = project.contract_amount or project.estimate_high
            if not amount or amount <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="No contract amount or estimate set on this project",
                )

            customer = project.customer
            if not customer or not customer.phone:
                raise HTTPException(
                    status_code=400,
                    detail="No customer phone number on this project",
                )

            # Look up company for Twilio number and name
            co_result = await session.execute(
                select(Company).where(Company.clerk_org_id == company_id)
            )
            company_record = co_result.scalar_one_or_none()

        company_name = company_record.name if company_record else "Your Contractor"
        from_phone = company_record.twilio_phone_number if company_record else None

        if not from_phone:
            raise HTTPException(
                status_code=400,
                detail="No Twilio phone number configured",
            )

        # Create Stripe payment link
        amount_cents = int(amount * 100)
        payment_url = await create_payment_link(
            amount_cents=amount_cents,
            description=f"Roofing project at {project.property_address}",
            customer_email=customer.email,
            metadata={
                "project_id": str(project_id),
                "company_id": company_id,
                "payment_type": "invoice",
            },
        )

        # Send via SMS
        customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "there"
        sms_body = (
            f"Hi {customer_name}, here's your invoice from {company_name} "
            f"for ${amount:,.2f} for work at {project.property_address}.\n\n"
            f"Pay securely here: {payment_url}\n\n"
            f"Questions? Just reply to this text."
        )

        twilio_sid = await send_sms(to=customer.phone, from_=from_phone, body=sms_body)

        # Update project status to invoiced
        async with get_tenant_session(company_id) as session:
            result = await session.execute(select(Project).where(Project.id == project_id))
            proj = result.scalar_one()
            proj.status = ProjectStatus.INVOICED
            await session.flush()

        return {
            "status": "sent",
            "payment_url": payment_url,
            "amount": amount,
            "twilio_sid": twilio_sid,
            "customer_phone": customer.phone,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("send_invoice failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Failed to send invoice: {e}")


from pydantic import BaseModel as PydanticBaseModel


class SupplierOrderRequest(PydanticBaseModel):
    supplier_email: str
    supplier_name: str = "Supplier"
    preferred_delivery_date: str = ""
    notes: str = ""


@router.post("/{project_id}/order-materials")
async def order_materials(
    project_id: uuid.UUID,
    data: SupplierOrderRequest,
    company_id: str = Depends(get_company_id),
):
    """Build material list from project SOW and send order to supplier."""
    from app.services.material_ordering import send_supplier_order_email

    try:
        result = await send_supplier_order_email(
            company_id=company_id,
            project_id=str(project_id),
            supplier_email=data.supplier_email,
            supplier_name=data.supplier_name,
            preferred_delivery_date=data.preferred_delivery_date,
            notes=data.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Material order failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=str(e))

    return result


@router.get("/{project_id}/material-list")
async def get_material_list(
    project_id: uuid.UUID,
    company_id: str = Depends(get_company_id),
):
    """Get the calculated material list for a project (no supplier contact)."""
    from app.services.material_ordering import build_material_list

    try:
        return await build_material_list(company_id, str(project_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
