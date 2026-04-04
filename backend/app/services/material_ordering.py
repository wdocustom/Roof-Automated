"""Material ordering service — analyzes SOW, builds material list, contacts supplier.

For now, suppliers are contacted via email (the universal channel).
Future: EDI/API integrations with ABC Supply, Beacon/QBP, SRS, etc.
"""

import json
import logging
from datetime import UTC, datetime
from email.mime.text import MIMEText

from sqlalchemy import select

from app.core.database import get_tenant_session
from app.models.company import Company
from app.models.project import Project
from app.models.rate_card import Material

logger = logging.getLogger(__name__)


async def build_material_list(company_id: str, project_id: str) -> dict:
    """Analyze the project SOW and build a detailed material list.

    Returns a dict with materials, quantities, and estimated cost.
    """
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        sqft = project.estimated_sqft or 1700.0
        project_type = project.project_type.value
        complexity = "moderate"  # TODO: pull from project metadata

        # Get materials from rate card
        result = await session.execute(
            select(Material).where(Material.is_active == True)  # noqa: E712
        )
        materials = result.scalars().all()

    # Calculate quantities based on sqft and project type
    squares = sqft / 100  # Roofing is measured in "squares" (100 sqft)
    material_list = []

    # Waste factor multiplier based on complexity
    waste_multipliers = {
        "simple": 1.10,
        "moderate": 1.15,
        "complex": 1.20,
        "very_complex": 1.25,
    }
    waste = waste_multipliers.get(complexity, 1.15)

    if "roof" in project_type:
        material_list = _calculate_roofing_materials(materials, squares, waste)
    elif "siding" in project_type:
        material_list = _calculate_siding_materials(materials, sqft, waste)
    else:
        material_list = _calculate_roofing_materials(materials, squares, waste)

    total_cost = sum(m["total_cost"] for m in material_list)

    return {
        "project_id": str(project_id),
        "project_type": project_type,
        "sqft": sqft,
        "squares": round(squares, 1),
        "complexity": complexity,
        "waste_factor": waste,
        "materials": material_list,
        "estimated_material_cost": round(total_cost, 2),
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _calculate_roofing_materials(
    materials: list, squares: float, waste: float
) -> list[dict]:
    """Calculate roofing material quantities."""
    items = []
    material_map = {m.category: m for m in materials}

    # Shingles — 3 bundles per square
    if shingle := material_map.get("shingles"):
        qty = round(squares * 3 * waste)
        items.append({
            "material": shingle.name,
            "category": "shingles",
            "quantity": qty,
            "unit": shingle.unit,
            "unit_price": float(shingle.price_per_unit),
            "total_cost": round(qty * float(shingle.price_per_unit), 2),
        })

    # Underlayment — 1 roll per 4 squares
    if underlay := material_map.get("underlayment"):
        qty = max(round(squares / 4 * waste), 1)
        items.append({
            "material": underlay.name,
            "category": "underlayment",
            "quantity": qty,
            "unit": underlay.unit,
            "unit_price": float(underlay.price_per_unit),
            "total_cost": round(qty * float(underlay.price_per_unit), 2),
        })

    # Ridge vent — 1 per 20 linear feet of ridge (estimate ridge = sqft^0.5 * 0.8)
    if ridge := material_map.get("ridge_vent"):
        ridge_feet = round((squares * 100) ** 0.5 * 0.8)
        qty = max(round(ridge_feet / 4 * waste), 1)  # 4ft sections
        items.append({
            "material": ridge.name,
            "category": "ridge_vent",
            "quantity": qty,
            "unit": ridge.unit,
            "unit_price": float(ridge.price_per_unit),
            "total_cost": round(qty * float(ridge.price_per_unit), 2),
        })

    # Ice & water shield — valleys + eaves (estimate 1-2 rolls per 10 squares)
    if ice := material_map.get("ice_water_shield"):
        qty = max(round(squares / 8 * waste), 1)
        items.append({
            "material": ice.name,
            "category": "ice_water_shield",
            "quantity": qty,
            "unit": ice.unit,
            "unit_price": float(ice.price_per_unit),
            "total_cost": round(qty * float(ice.price_per_unit), 2),
        })

    # Drip edge — perimeter (estimate perimeter = 4 * sqrt(sqft))
    if drip := material_map.get("drip_edge"):
        perimeter_ft = round(4 * (squares * 100) ** 0.5)
        qty = max(round(perimeter_ft / 10 * waste), 1)  # 10ft pieces
        items.append({
            "material": drip.name,
            "category": "drip_edge",
            "quantity": qty,
            "unit": drip.unit,
            "unit_price": float(drip.price_per_unit),
            "total_cost": round(qty * float(drip.price_per_unit), 2),
        })

    # Flashing
    if flashing := material_map.get("flashing"):
        qty = max(round(squares * 0.5 * waste), 2)
        items.append({
            "material": flashing.name,
            "category": "flashing",
            "quantity": qty,
            "unit": flashing.unit,
            "unit_price": float(flashing.price_per_unit),
            "total_cost": round(qty * float(flashing.price_per_unit), 2),
        })

    # Nails — ~320 nails per square (2 boxes per 10 squares)
    if nails := material_map.get("nails"):
        qty = max(round(squares / 5 * waste), 1)
        items.append({
            "material": nails.name,
            "category": "nails",
            "quantity": qty,
            "unit": nails.unit,
            "unit_price": float(nails.price_per_unit),
            "total_cost": round(qty * float(nails.price_per_unit), 2),
        })

    return items


def _calculate_siding_materials(
    materials: list, sqft: float, waste: float
) -> list[dict]:
    """Calculate siding material quantities."""
    items = []
    material_map = {m.category: m for m in materials}

    if siding := material_map.get("vinyl_siding"):
        # 2 squares per 200 sqft of wall area
        squares = sqft / 100
        qty = max(round(squares * waste), 1)
        items.append({
            "material": siding.name,
            "category": "vinyl_siding",
            "quantity": qty,
            "unit": siding.unit,
            "unit_price": float(siding.price_per_unit),
            "total_cost": round(qty * float(siding.price_per_unit), 2),
        })

    if trim := material_map.get("trim"):
        qty = max(round(sqft / 50 * waste), 2)
        items.append({
            "material": trim.name,
            "category": "trim",
            "quantity": qty,
            "unit": trim.unit,
            "unit_price": float(trim.price_per_unit),
            "total_cost": round(qty * float(trim.price_per_unit), 2),
        })

    return items


async def generate_supplier_email(
    company_id: str,
    project_id: str,
    supplier_email: str,
    supplier_name: str = "Supplier",
    preferred_delivery_date: str = "",
    notes: str = "",
) -> dict:
    """Generate and return a supplier order email.

    Does NOT send the email — returns the content so the contractor can
    review and the system can send via whatever email service is configured.
    """
    material_list = await build_material_list(company_id, project_id)

    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()

        co_result = await session.execute(
            select(Company).where(Company.clerk_org_id == company_id)
        )
        company = co_result.scalar_one_or_none()

    company_name = company.name if company else "Contractor"
    company_phone = company.phone if company else ""
    property_addr = project.property_address if project else "TBD"
    property_full = (
        f"{project.property_address}, {project.property_city}, "
        f"{project.property_state} {project.property_zip}"
        if project
        else "TBD"
    )

    # Build materials table for email
    materials_text = ""
    for m in material_list["materials"]:
        materials_text += (
            f"  - {m['quantity']} {m['unit']} {m['material']} "
            f"(${m['unit_price']:.2f}/ea = ${m['total_cost']:.2f})\n"
        )

    delivery_line = ""
    if preferred_delivery_date:
        delivery_line = f"\nPreferred Delivery Date: {preferred_delivery_date}"

    notes_line = ""
    if notes:
        notes_line = f"\nAdditional Notes: {notes}"

    subject = f"Material Order — {company_name} — {property_addr}"

    body = f"""Hi {supplier_name},

We'd like to place the following material order for an upcoming project.

Company: {company_name}
Job Site: {property_full}
Project Type: {material_list['project_type'].replace('_', ' ').title()}
Estimated Area: {material_list['sqft']:,.0f} sq ft ({material_list['squares']:.1f} squares)
{delivery_line}
{notes_line}

Materials Needed:
{materials_text}
Estimated Total: ${material_list['estimated_material_cost']:,.2f}
(Quantities include {int((material_list['waste_factor'] - 1) * 100)}% waste factor)

Please confirm:
1. Material availability and any substitutions needed
2. Pricing (account pricing if applicable)
3. Earliest delivery date to job site

Delivery address: {property_full}

Please reply to this email or call {company_phone} to confirm.

Thanks,
{company_name}
"""

    return {
        "to": supplier_email,
        "subject": subject,
        "body": body.strip(),
        "materials": material_list,
        "project_id": str(project_id),
    }


async def send_supplier_order_email(
    company_id: str,
    project_id: str,
    supplier_email: str,
    supplier_name: str = "Supplier",
    preferred_delivery_date: str = "",
    notes: str = "",
) -> dict:
    """Generate and send the supplier order email.

    Uses SMTP if configured, otherwise returns the email for manual sending.
    """
    import smtplib

    from app.core.config import settings

    email_data = await generate_supplier_email(
        company_id=company_id,
        project_id=project_id,
        supplier_email=supplier_email,
        supplier_name=supplier_name,
        preferred_delivery_date=preferred_delivery_date,
        notes=notes,
    )

    # Try to send via SMTP if configured
    smtp_host = getattr(settings, "smtp_host", None)
    smtp_from = getattr(settings, "smtp_from_email", None)

    if smtp_host and smtp_from:
        try:
            msg = MIMEText(email_data["body"])
            msg["Subject"] = email_data["subject"]
            msg["From"] = smtp_from
            msg["To"] = supplier_email

            smtp_port = getattr(settings, "smtp_port", 587)
            smtp_user = getattr(settings, "smtp_user", smtp_from)
            smtp_pass = getattr(settings, "smtp_password", "")

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                if smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)

            email_data["sent"] = True
            logger.info("supplier_email_sent", to=supplier_email, project_id=project_id)
        except Exception:
            logger.exception("supplier_email_failed", to=supplier_email)
            email_data["sent"] = False
            email_data["send_error"] = "SMTP send failed — email content returned for manual sending"
    else:
        email_data["sent"] = False
        email_data["send_error"] = "SMTP not configured — email content returned for manual sending"

    return email_data
