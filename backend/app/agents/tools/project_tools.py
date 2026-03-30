"""Project and customer management tools for LangGraph agents."""

import uuid

from langchain_core.tools import tool
from sqlalchemy import select

from app.core.database import get_tenant_session
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User, UserRole


@tool
async def create_lead_project(
    company_id: str,
    customer_phone: str,
    property_address: str,
    property_city: str,
    property_state: str,
    property_zip: str,
    project_type: str = "roof_replacement",
    description: str = "",
    lead_source: str = "sms",
) -> dict:
    """Create a new project from a lead intake and ensure a customer record exists.

    Args:
        company_id: Tenant company ID.
        customer_phone: Customer's phone number.
        property_address: Property street address.
        property_city: City.
        property_state: 2-letter state code.
        property_zip: ZIP code.
        project_type: Type of project.
        description: Initial description/notes.
        lead_source: How the lead came in.

    Returns:
        Dict with project_id and customer_id.
    """
    async with get_tenant_session(company_id) as session:
        # Find or create customer by phone
        result = await session.execute(
            select(User).where(User.phone == customer_phone, User.company_id == company_id)
        )
        customer = result.scalar_one_or_none()

        if not customer:
            customer = User(
                company_id=company_id,
                clerk_user_id=f"lead_{uuid.uuid4().hex[:12]}",
                email=f"{customer_phone.replace('+', '')}@placeholder.local",
                phone=customer_phone,
                role=UserRole.CUSTOMER,
            )
            session.add(customer)
            await session.flush()

        project = Project(
            company_id=company_id,
            customer_id=customer.id,
            property_address=property_address,
            property_city=property_city,
            property_state=property_state,
            property_zip=property_zip,
            project_type=ProjectType(project_type),
            status=ProjectStatus.LEAD,
            description=description,
            lead_source=lead_source,
        )
        session.add(project)
        await session.flush()

        return {
            "project_id": str(project.id),
            "customer_id": str(customer.id),
            "status": "lead",
        }


@tool
async def update_project_status(
    company_id: str,
    project_id: str,
    new_status: str,
) -> dict:
    """Update a project's status in the pipeline.

    Args:
        company_id: Tenant company ID.
        project_id: Project UUID.
        new_status: New status value (e.g., 'estimated', 'contract_sent').

    Returns:
        Dict with updated status.
    """
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project).where(Project.id == uuid.UUID(project_id))
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "Project not found"}

        project.status = ProjectStatus(new_status)
        await session.flush()
        return {"project_id": project_id, "status": new_status}


@tool
async def update_project_estimate(
    company_id: str,
    project_id: str,
    estimate_low: float,
    estimate_high: float,
    estimated_sqft: float | None = None,
) -> dict:
    """Update a project's preliminary estimate range.

    Args:
        company_id: Tenant company ID.
        project_id: Project UUID.
        estimate_low: Low end of estimate range.
        estimate_high: High end of estimate range.
        estimated_sqft: Estimated square footage.

    Returns:
        Dict confirming the update.
    """
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project).where(Project.id == uuid.UUID(project_id))
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "Project not found"}

        project.estimate_low = estimate_low
        project.estimate_high = estimate_high
        if estimated_sqft:
            project.estimated_sqft = estimated_sqft
        project.status = ProjectStatus.ESTIMATED
        await session.flush()

        return {
            "project_id": project_id,
            "estimate_low": estimate_low,
            "estimate_high": estimate_high,
            "status": "estimated",
        }


@tool
async def get_project_details(
    company_id: str,
    project_id: str,
) -> dict:
    """Get full project details including current status and estimates.

    Args:
        company_id: Tenant company ID.
        project_id: Project UUID.

    Returns:
        Dict with all project fields.
    """
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project).where(Project.id == uuid.UUID(project_id))
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "Project not found"}

        return {
            "project_id": str(project.id),
            "status": project.status.value,
            "project_type": project.project_type.value,
            "property_address": project.property_address,
            "property_city": project.property_city,
            "property_state": project.property_state,
            "property_zip": project.property_zip,
            "estimated_sqft": project.estimated_sqft,
            "estimate_low": project.estimate_low,
            "estimate_high": project.estimate_high,
            "contract_amount": project.contract_amount,
            "description": project.description,
        }
