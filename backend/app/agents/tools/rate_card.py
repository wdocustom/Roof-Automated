"""Rate card lookup tools for LangGraph agents.

These tools allow agents to query the company's pricing data to
generate accurate preliminary estimates.
"""

from langchain_core.tools import tool
from sqlalchemy import select

from app.core.database import get_tenant_session
from app.models.rate_card import (
    LaborRate,
    Material,
    PermitFee,
    WasteFactor,
)


@tool
async def lookup_materials(
    company_id: str,
    category: str,
) -> list[dict]:
    """Look up active materials and pricing for a given category.

    Args:
        company_id: The tenant company ID.
        category: Material category (e.g., 'shingles', 'underlayment', 'flashing').

    Returns:
        List of materials with name, unit_cost, unit_type, waste factors.
    """
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Material)
            .where(Material.category == category, Material.is_active.is_(True))
            .order_by(Material.unit_cost)
        )
        materials = result.scalars().all()

        return [
            {
                "id": str(m.id),
                "name": m.name,
                "category": m.category.value,
                "unit_type": m.unit_type.value,
                "unit_cost": m.unit_cost,
                "units_per_square": m.units_per_square,
                "manufacturer": m.manufacturer,
                "supplier_name": m.supplier_name,
            }
            for m in materials
        ]


@tool
async def lookup_labor_rates(
    company_id: str,
    task_type: str,
) -> list[dict]:
    """Look up labor rates for a given task type.

    Args:
        company_id: The tenant company ID.
        task_type: Labor task (e.g., 'tear_off', 'install_shingles').

    Returns:
        List of labor rates with base_rate, adjustments, markup.
    """
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(LaborRate).where(LaborRate.task_type == task_type, LaborRate.is_active.is_(True))
        )
        rates = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "task_type": r.task_type.value,
                "rate_unit": r.rate_unit.value,
                "base_rate": r.base_rate,
                "crew_size_standard": r.crew_size_standard,
                "markup_pct": r.markup_pct,
                "region_adjustment_pct": r.region_adjustment_pct,
            }
            for r in rates
        ]


@tool
async def lookup_waste_factor(
    company_id: str,
    material_category: str,
    roof_complexity: str = "moderate",
) -> dict:
    """Look up waste factor percentage for a material + complexity combo.

    Args:
        company_id: The tenant company ID.
        material_category: e.g., 'shingles'.
        roof_complexity: 'simple', 'moderate', 'complex', 'very_complex'.

    Returns:
        Dict with waste_percentage.
    """
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(WasteFactor).where(
                WasteFactor.material_category == material_category,
                WasteFactor.roof_complexity == roof_complexity,
            )
        )
        wf = result.scalar_one_or_none()

        if wf:
            return {"waste_percentage": wf.waste_percentage}
        # Default fallback
        return {"waste_percentage": 10.0}


@tool
async def lookup_permit_fees(
    company_id: str,
    zip_code: str,
    permit_type: str = "roofing",
) -> dict:
    """Look up permit fees for a jurisdiction.

    Args:
        company_id: The tenant company ID.
        zip_code: Property ZIP code.
        permit_type: 'roofing' or 'siding'.

    Returns:
        Dict with base_fee and per_sqft_fee.
    """
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(PermitFee).where(
                PermitFee.zip_code == zip_code,
                PermitFee.permit_type == permit_type,
                PermitFee.is_active.is_(True),
            )
        )
        fee = result.scalar_one_or_none()

        if fee:
            return {
                "base_fee": fee.base_fee,
                "per_sqft_fee": fee.per_sqft_fee,
                "state": fee.state,
            }
        return {"base_fee": 0.0, "per_sqft_fee": 0.0, "state": "unknown"}
