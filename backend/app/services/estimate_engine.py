"""Preliminary Estimate Engine — generates range estimates from rate cards.

This is the core pricing logic. It takes property measurements and the
company's rate card data to produce a preliminary estimate range.

CRITICAL: All estimates include explicit disclaimers. They are NOT binding.
High-value estimates trigger human review per company threshold.
"""

from dataclasses import dataclass, field

from sqlalchemy import select

from app.core.database import get_tenant_session
from app.models.rate_card import (
    LaborRate,
    LaborTaskType,
    Material,
    MaterialCategory,
    PermitFee,
    WasteFactor,
)


@dataclass
class EstimateLineItem:
    """A single line item in the estimate breakdown."""

    category: str
    description: str
    quantity: float
    unit: str
    unit_cost: float
    waste_pct: float = 0.0
    subtotal: float = 0.0

    def __post_init__(self):
        adjusted_qty = self.quantity * (1 + self.waste_pct / 100)
        self.subtotal = round(adjusted_qty * self.unit_cost, 2)


@dataclass
class EstimateResult:
    """Complete preliminary estimate with breakdown and disclaimers."""

    project_type: str
    total_sqft: float
    roof_complexity: str
    materials: list[EstimateLineItem] = field(default_factory=list)
    labor: list[EstimateLineItem] = field(default_factory=list)
    permit_fees: float = 0.0
    materials_total: float = 0.0
    labor_total: float = 0.0
    subtotal: float = 0.0
    markup_pct: float = 0.0
    total_low: float = 0.0
    total_high: float = 0.0
    confidence: float = 0.0
    disclaimers: list[str] = field(default_factory=list)
    requires_human_review: bool = False
    human_review_reason: str = ""

    def calculate_totals(self, variance_pct: float = 15.0):
        """Calculate totals with a variance range for the preliminary estimate."""
        self.materials_total = round(sum(item.subtotal for item in self.materials), 2)
        self.labor_total = round(sum(item.subtotal for item in self.labor), 2)
        self.subtotal = round(self.materials_total + self.labor_total + self.permit_fees, 2)

        # Apply markup
        marked_up = self.subtotal * (1 + self.markup_pct / 100)

        # Range: ±variance_pct
        self.total_low = round(marked_up * (1 - variance_pct / 100), 2)
        self.total_high = round(marked_up * (1 + variance_pct / 100), 2)


STANDARD_DISCLAIMER = (
    "This is a preliminary range estimate based on available data. "
    "Final pricing requires an on-site inspection and is subject to change. "
    "This estimate is not a binding contract or guarantee of price."
)

PHOTO_ONLY_DISCLAIMER = (
    "Estimate based on photo analysis only — accuracy may vary. "
    "Professional measurements (EagleView/on-site) recommended for final pricing."
)


async def generate_roof_estimate(
    company_id: str,
    total_sqft: float,
    roof_complexity: str = "moderate",
    zip_code: str = "",
    include_tear_off: bool = True,
    measurement_source: str = "manual",
) -> EstimateResult:
    """Generate a preliminary roof replacement estimate from rate cards.

    Args:
        company_id: Tenant company ID.
        total_sqft: Total roof area in square feet.
        roof_complexity: simple/moderate/complex/very_complex.
        zip_code: For permit fee lookup.
        include_tear_off: Whether to include tear-off labor.
        measurement_source: 'manual', 'photo', 'eagleview'.

    Returns:
        EstimateResult with full breakdown and disclaimers.
    """
    squares = total_sqft / 100  # Standard roofing unit

    estimate = EstimateResult(
        project_type="roof_replacement",
        total_sqft=total_sqft,
        roof_complexity=roof_complexity,
    )

    estimate.disclaimers.append(STANDARD_DISCLAIMER)
    if measurement_source == "photo":
        estimate.disclaimers.append(PHOTO_ONLY_DISCLAIMER)
        estimate.confidence = 0.5
    elif measurement_source == "manual":
        estimate.confidence = 0.6
    else:
        estimate.confidence = 0.8

    async with get_tenant_session(company_id) as session:
        # --- Materials ---
        material_categories = [
            MaterialCategory.SHINGLES,
            MaterialCategory.UNDERLAYMENT,
            MaterialCategory.FLASHING,
            MaterialCategory.RIDGE_VENT,
            MaterialCategory.ICE_WATER_SHIELD,
            MaterialCategory.DRIP_EDGE,
            MaterialCategory.NAILS_FASTENERS,
        ]

        for cat in material_categories:
            # Get cheapest active material in category
            result = await session.execute(
                select(Material)
                .where(Material.category == cat, Material.is_active.is_(True))
                .order_by(Material.unit_cost)
                .limit(1)
            )
            material = result.scalar_one_or_none()
            if not material:
                continue

            # Get waste factor
            result = await session.execute(
                select(WasteFactor).where(
                    WasteFactor.material_category == cat,
                    WasteFactor.roof_complexity == roof_complexity,
                )
            )
            wf = result.scalar_one_or_none()
            waste_pct = wf.waste_percentage if wf else 10.0

            # Calculate quantity based on unit type
            if material.units_per_square and material.units_per_square > 0:
                qty = squares * material.units_per_square
            else:
                qty = squares

            estimate.materials.append(
                EstimateLineItem(
                    category=cat.value,
                    description=material.name,
                    quantity=round(qty, 1),
                    unit=material.unit_type.value,
                    unit_cost=material.unit_cost,
                    waste_pct=waste_pct,
                )
            )

        # --- Labor ---
        labor_tasks = [LaborTaskType.INSTALL_SHINGLES, LaborTaskType.CLEANUP]
        if include_tear_off:
            labor_tasks.insert(0, LaborTaskType.TEAR_OFF)

        avg_markup = 0.0
        labor_count = 0

        for task in labor_tasks:
            result = await session.execute(
                select(LaborRate)
                .where(LaborRate.task_type == task, LaborRate.is_active.is_(True))
                .limit(1)
            )
            rate = result.scalar_one_or_none()
            if not rate:
                continue

            # Most roofing labor is per-square
            qty = squares if rate.rate_unit.value == "per_square" else total_sqft

            adjusted_rate = rate.base_rate * (1 + rate.region_adjustment_pct / 100)

            estimate.labor.append(
                EstimateLineItem(
                    category=task.value,
                    description=f"Labor: {task.value.replace('_', ' ').title()}",
                    quantity=round(qty, 1),
                    unit=rate.rate_unit.value,
                    unit_cost=round(adjusted_rate, 2),
                )
            )

            avg_markup += rate.markup_pct
            labor_count += 1

        estimate.markup_pct = round(avg_markup / max(labor_count, 1), 1)

        # --- Permit Fees ---
        if zip_code:
            result = await session.execute(
                select(PermitFee).where(
                    PermitFee.zip_code == zip_code,
                    PermitFee.permit_type == "roofing",
                    PermitFee.is_active.is_(True),
                )
            )
            permit = result.scalar_one_or_none()
            if permit:
                estimate.permit_fees = round(
                    permit.base_fee + (permit.per_sqft_fee * total_sqft), 2
                )

    # Calculate totals
    estimate.calculate_totals(variance_pct=15.0)

    return estimate


async def generate_siding_estimate(
    company_id: str,
    total_sqft: float,
    zip_code: str = "",
    measurement_source: str = "manual",
) -> EstimateResult:
    """Generate a preliminary siding estimate from rate cards.

    Similar structure to roof estimate but with siding-specific categories.
    """
    estimate = EstimateResult(
        project_type="siding_install",
        total_sqft=total_sqft,
        roof_complexity="moderate",  # Not applicable for siding, use as generic
    )

    estimate.disclaimers.append(STANDARD_DISCLAIMER)
    if measurement_source == "photo":
        estimate.disclaimers.append(PHOTO_ONLY_DISCLAIMER)
        estimate.confidence = 0.4  # Lower confidence for siding from photos
    else:
        estimate.confidence = 0.6

    async with get_tenant_session(company_id) as session:
        # Siding materials
        for cat in [MaterialCategory.SIDING_VINYL, MaterialCategory.TRIM, MaterialCategory.SOFFIT]:
            result = await session.execute(
                select(Material)
                .where(Material.category == cat, Material.is_active.is_(True))
                .order_by(Material.unit_cost)
                .limit(1)
            )
            material = result.scalar_one_or_none()
            if not material:
                continue

            estimate.materials.append(
                EstimateLineItem(
                    category=cat.value,
                    description=material.name,
                    quantity=round(total_sqft, 1),
                    unit=material.unit_type.value,
                    unit_cost=material.unit_cost,
                    waste_pct=10.0,
                )
            )

        # Labor
        result = await session.execute(
            select(LaborRate)
            .where(
                LaborRate.task_type == LaborTaskType.INSTALL_SIDING, LaborRate.is_active.is_(True)
            )
            .limit(1)
        )
        rate = result.scalar_one_or_none()
        if rate:
            estimate.labor.append(
                EstimateLineItem(
                    category="install_siding",
                    description="Labor: Siding Installation",
                    quantity=round(total_sqft, 1),
                    unit=rate.rate_unit.value,
                    unit_cost=rate.base_rate,
                )
            )
            estimate.markup_pct = rate.markup_pct

        # Permit
        if zip_code:
            result = await session.execute(
                select(PermitFee).where(
                    PermitFee.zip_code == zip_code,
                    PermitFee.permit_type == "siding",
                    PermitFee.is_active.is_(True),
                )
            )
            permit = result.scalar_one_or_none()
            if permit:
                estimate.permit_fees = round(
                    permit.base_fee + (permit.per_sqft_fee * total_sqft), 2
                )

    estimate.calculate_totals(variance_pct=20.0)  # Higher variance for siding
    return estimate


def format_estimate_for_sms(estimate: EstimateResult) -> str:
    """Format an estimate result into a customer-friendly SMS message."""
    lines = [
        f"📋 Preliminary Estimate — {estimate.project_type.replace('_', ' ').title()}",
        f"Area: {estimate.total_sqft:,.0f} sq ft",
        "",
        f"Estimated Range: ${estimate.total_low:,.0f} – ${estimate.total_high:,.0f}",
        "",
        "Breakdown:",
        f"  Materials: ${estimate.materials_total:,.0f}",
        f"  Labor: ${estimate.labor_total:,.0f}",
    ]

    if estimate.permit_fees > 0:
        lines.append(f"  Permits: ${estimate.permit_fees:,.0f}")

    lines.append("")
    lines.append(estimate.disclaimers[0])

    if estimate.requires_human_review:
        lines.append("")
        lines.append("⚠️ A team member will review this estimate and follow up shortly.")

    return "\n".join(lines)
