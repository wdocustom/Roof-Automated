"""Seed a company's rate card with industry-standard pricing.

Called during onboarding or from admin. Provides reasonable defaults
for Midwest US pricing (2026). Companies customize in Settings later.

These are real-world-informed defaults:
- Shingle pricing: $90-120/square (3-tab to architectural)
- Labor: $75-95/square for tear-off, $85-110 for install
- Markup: 30-40% standard for roofing contractors
"""

from app.core.database import get_tenant_session
from app.models.rate_card import (
    LaborRate,
    LaborRateUnit,
    LaborTaskType,
    Material,
    MaterialCategory,
    PermitFee,
    UnitType,
    WasteFactor,
)


async def seed_rate_card(company_id: str) -> dict:
    """Populate a company's rate card with industry defaults.

    Returns a summary of what was seeded.
    """
    counts = {"materials": 0, "labor": 0, "waste_factors": 0, "permits": 0}

    async with get_tenant_session(company_id) as session:
        # ── Materials ──────────────────────────────────────────
        materials = [
            # Shingles
            Material(
                company_id=company_id,
                category=MaterialCategory.SHINGLES,
                name="GAF Timberline HDZ (Architectural)",
                manufacturer="GAF",
                unit_type=UnitType.BUNDLE,
                unit_cost=42.00,
                units_per_square=3.0,
                supplier_name="ABC Supply",
            ),
            # Underlayment
            Material(
                company_id=company_id,
                category=MaterialCategory.UNDERLAYMENT,
                name="GAF FeltBuster Synthetic Underlayment",
                manufacturer="GAF",
                unit_type=UnitType.ROLL,
                unit_cost=65.00,
                units_per_square=0.4,
                supplier_name="ABC Supply",
            ),
            # Flashing
            Material(
                company_id=company_id,
                category=MaterialCategory.FLASHING,
                name="Aluminum Step Flashing 4x4",
                unit_type=UnitType.PIECE,
                unit_cost=1.50,
                units_per_square=8.0,
                supplier_name="ABC Supply",
            ),
            # Ridge vent
            Material(
                company_id=company_id,
                category=MaterialCategory.RIDGE_VENT,
                name="GAF Cobra Ridge Vent",
                manufacturer="GAF",
                unit_type=UnitType.LINEAR_FOOT,
                unit_cost=2.75,
                units_per_square=3.0,
                supplier_name="ABC Supply",
            ),
            # Ice & water shield
            Material(
                company_id=company_id,
                category=MaterialCategory.ICE_WATER_SHIELD,
                name="GAF WeatherWatch Ice & Water Shield",
                manufacturer="GAF",
                unit_type=UnitType.ROLL,
                unit_cost=95.00,
                units_per_square=0.25,
                supplier_name="ABC Supply",
            ),
            # Drip edge
            Material(
                company_id=company_id,
                category=MaterialCategory.DRIP_EDGE,
                name="Aluminum Drip Edge 10ft",
                unit_type=UnitType.PIECE,
                unit_cost=5.50,
                units_per_square=2.0,
                supplier_name="ABC Supply",
            ),
            # Nails/fasteners
            Material(
                company_id=company_id,
                category=MaterialCategory.NAILS_FASTENERS,
                name="Roofing Nails 1-1/4\" Coil",
                unit_type=UnitType.BOX,
                unit_cost=45.00,
                units_per_square=0.25,
                supplier_name="ABC Supply",
            ),
            # Siding
            Material(
                company_id=company_id,
                category=MaterialCategory.SIDING_VINYL,
                name='CertainTeed Monogram 4.5" Double',
                manufacturer="CertainTeed",
                unit_type=UnitType.SQUARE,
                unit_cost=125.00,
                units_per_square=1.0,
            ),
            Material(
                company_id=company_id,
                category=MaterialCategory.TRIM,
                name="Vinyl J-Channel / Trim Package",
                unit_type=UnitType.LINEAR_FOOT,
                unit_cost=1.85,
                units_per_square=10.0,
            ),
            Material(
                company_id=company_id,
                category=MaterialCategory.SOFFIT,
                name="Vinyl Soffit Panel",
                unit_type=UnitType.SQUARE_FOOT,
                unit_cost=3.50,
                units_per_square=1.0,
            ),
        ]

        for m in materials:
            session.add(m)
        counts["materials"] = len(materials)

        # ── Labor Rates ────────────────────────────────────────
        labor_rates = [
            LaborRate(
                company_id=company_id,
                task_type=LaborTaskType.TEAR_OFF,
                description="Remove existing shingles, underlayment, and debris",
                rate_unit=LaborRateUnit.PER_SQUARE,
                base_rate=85.00,
                crew_size_standard=4,
                markup_pct=35.0,
            ),
            LaborRate(
                company_id=company_id,
                task_type=LaborTaskType.INSTALL_SHINGLES,
                description="Install new shingles with proper nailing pattern",
                rate_unit=LaborRateUnit.PER_SQUARE,
                base_rate=95.00,
                crew_size_standard=4,
                markup_pct=35.0,
            ),
            LaborRate(
                company_id=company_id,
                task_type=LaborTaskType.INSTALL_UNDERLAYMENT,
                description="Install synthetic underlayment",
                rate_unit=LaborRateUnit.PER_SQUARE,
                base_rate=25.00,
                crew_size_standard=3,
                markup_pct=35.0,
            ),
            LaborRate(
                company_id=company_id,
                task_type=LaborTaskType.INSTALL_FLASHING,
                description="Install step flashing, counter flashing, valley flashing",
                rate_unit=LaborRateUnit.PER_LINEAR_FOOT,
                base_rate=12.00,
                markup_pct=35.0,
            ),
            LaborRate(
                company_id=company_id,
                task_type=LaborTaskType.CLEANUP,
                description="Job site cleanup, magnetic nail sweep, haul-off",
                rate_unit=LaborRateUnit.PER_SQUARE,
                base_rate=15.00,
                crew_size_standard=2,
                markup_pct=35.0,
            ),
            LaborRate(
                company_id=company_id,
                task_type=LaborTaskType.INSTALL_SIDING,
                description="Vinyl siding installation per square foot",
                rate_unit=LaborRateUnit.PER_SQUARE,
                base_rate=175.00,
                crew_size_standard=3,
                markup_pct=30.0,
            ),
            LaborRate(
                company_id=company_id,
                task_type=LaborTaskType.INSTALL_GUTTERS,
                description="Seamless gutter installation per linear foot",
                rate_unit=LaborRateUnit.PER_LINEAR_FOOT,
                base_rate=8.50,
                crew_size_standard=2,
                markup_pct=30.0,
            ),
        ]

        for lr in labor_rates:
            session.add(lr)
        counts["labor"] = len(labor_rates)

        # ── Waste Factors ──────────────────────────────────────
        waste_data = [
            # Shingles waste by complexity
            (MaterialCategory.SHINGLES, "simple", 7.0),
            (MaterialCategory.SHINGLES, "moderate", 12.0),
            (MaterialCategory.SHINGLES, "complex", 17.0),
            (MaterialCategory.SHINGLES, "very_complex", 22.0),
            # Underlayment
            (MaterialCategory.UNDERLAYMENT, "simple", 5.0),
            (MaterialCategory.UNDERLAYMENT, "moderate", 8.0),
            (MaterialCategory.UNDERLAYMENT, "complex", 12.0),
            (MaterialCategory.UNDERLAYMENT, "very_complex", 15.0),
            # Flashing
            (MaterialCategory.FLASHING, "simple", 5.0),
            (MaterialCategory.FLASHING, "moderate", 10.0),
            (MaterialCategory.FLASHING, "complex", 15.0),
            (MaterialCategory.FLASHING, "very_complex", 20.0),
            # Ridge vent
            (MaterialCategory.RIDGE_VENT, "simple", 5.0),
            (MaterialCategory.RIDGE_VENT, "moderate", 5.0),
            (MaterialCategory.RIDGE_VENT, "complex", 10.0),
            (MaterialCategory.RIDGE_VENT, "very_complex", 10.0),
            # Ice & water
            (MaterialCategory.ICE_WATER_SHIELD, "simple", 5.0),
            (MaterialCategory.ICE_WATER_SHIELD, "moderate", 8.0),
            (MaterialCategory.ICE_WATER_SHIELD, "complex", 10.0),
            (MaterialCategory.ICE_WATER_SHIELD, "very_complex", 12.0),
            # Drip edge
            (MaterialCategory.DRIP_EDGE, "simple", 5.0),
            (MaterialCategory.DRIP_EDGE, "moderate", 5.0),
            (MaterialCategory.DRIP_EDGE, "complex", 8.0),
            (MaterialCategory.DRIP_EDGE, "very_complex", 10.0),
            # Nails
            (MaterialCategory.NAILS_FASTENERS, "simple", 5.0),
            (MaterialCategory.NAILS_FASTENERS, "moderate", 5.0),
            (MaterialCategory.NAILS_FASTENERS, "complex", 8.0),
            (MaterialCategory.NAILS_FASTENERS, "very_complex", 10.0),
        ]

        for cat, complexity, pct in waste_data:
            session.add(
                WasteFactor(
                    company_id=company_id,
                    material_category=cat,
                    roof_complexity=complexity,
                    waste_percentage=pct,
                )
            )
        counts["waste_factors"] = len(waste_data)

        # ── Default permit fees (Omaha / Nebraska) ─────────────
        permit_fees = [
            PermitFee(
                company_id=company_id,
                state="NE",
                zip_code="68102",
                city="Omaha",
                permit_type="roofing",
                base_fee=150.00,
                per_sqft_fee=0.0,
            ),
            PermitFee(
                company_id=company_id,
                state="NE",
                zip_code="68102",
                city="Omaha",
                permit_type="siding",
                base_fee=125.00,
                per_sqft_fee=0.0,
            ),
        ]

        for pf in permit_fees:
            session.add(pf)
        counts["permits"] = len(permit_fees)

    return counts
