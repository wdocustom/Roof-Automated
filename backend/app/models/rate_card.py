"""Rate card and material pricing models — the backbone of all estimates.

This is the most important data structure in the platform. Every AI-generated
estimate flows through these tables. Accuracy here = trust = adoption.
"""

import enum
import uuid

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TenantMixin

# ---------------------------------------------------------------------------
# Rate Card Versioning — audit trail for all pricing changes
# ---------------------------------------------------------------------------


class RateCardVersion(BaseModel, TenantMixin):
    """Snapshot of when rate cards were last updated. Supports audit trail."""

    __tablename__ = "rate_card_versions"

    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    effective_date: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------


class MaterialCategory(enum.StrEnum):
    SHINGLES = "shingles"
    UNDERLAYMENT = "underlayment"
    FLASHING = "flashing"
    RIDGE_VENT = "ridge_vent"
    ICE_WATER_SHIELD = "ice_water_shield"
    DRIP_EDGE = "drip_edge"
    NAILS_FASTENERS = "nails_fasteners"
    SIDING_VINYL = "siding_vinyl"
    SIDING_FIBER_CEMENT = "siding_fiber_cement"
    SIDING_WOOD = "siding_wood"
    TRIM = "trim"
    SOFFIT = "soffit"
    GUTTERS = "gutters"
    OTHER = "other"


class UnitType(enum.StrEnum):
    SQUARE = "square"  # 100 sq ft (roofing standard)
    BUNDLE = "bundle"
    LINEAR_FOOT = "linear_foot"
    SQUARE_FOOT = "square_foot"
    PIECE = "piece"
    ROLL = "roll"
    BOX = "box"


class Material(BaseModel, TenantMixin):
    """Material with pricing, supplier, and waste factor."""

    __tablename__ = "materials"

    category: Mapped[MaterialCategory] = mapped_column(
        Enum(MaterialCategory, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(String(255))
    sku: Mapped[str | None] = mapped_column(String(100))

    # Pricing
    unit_type: Mapped[UnitType] = mapped_column(
        Enum(UnitType, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    units_per_square: Mapped[float | None] = mapped_column(Float)  # conversion factor

    # Supplier
    supplier_name: Mapped[str | None] = mapped_column(String(255))
    supplier_part_number: Mapped[str | None] = mapped_column(String(100))

    # Versioning
    rate_card_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rate_card_versions.id")
    )
    rate_card_version = relationship("RateCardVersion")

    is_active: Mapped[bool] = mapped_column(default=True)


# ---------------------------------------------------------------------------
# Waste Factors — vary by material category and roof complexity
# ---------------------------------------------------------------------------


class RoofComplexity(enum.StrEnum):
    SIMPLE = "simple"  # Gable, few penetrations
    MODERATE = "moderate"  # Hip, some valleys/penetrations
    COMPLEX = "complex"  # Cut-up, many valleys/dormers
    VERY_COMPLEX = "very_complex"  # Mansard, turrets, steep pitch


class WasteFactor(BaseModel, TenantMixin):
    """Waste percentage by material category and roof complexity."""

    __tablename__ = "waste_factors"

    material_category: Mapped[MaterialCategory] = mapped_column(
        Enum(MaterialCategory, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    roof_complexity: Mapped[RoofComplexity] = mapped_column(
        Enum(RoofComplexity, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    waste_percentage: Mapped[float] = mapped_column(Float, nullable=False)  # e.g., 15.0 = 15%


# ---------------------------------------------------------------------------
# Labor Rates
# ---------------------------------------------------------------------------


class LaborTaskType(enum.StrEnum):
    TEAR_OFF = "tear_off"
    INSTALL_SHINGLES = "install_shingles"
    INSTALL_UNDERLAYMENT = "install_underlayment"
    INSTALL_FLASHING = "install_flashing"
    INSTALL_SIDING = "install_siding"
    INSTALL_TRIM = "install_trim"
    INSTALL_GUTTERS = "install_gutters"
    REPAIR_PATCH = "repair_patch"
    INSPECTION = "inspection"
    CLEANUP = "cleanup"
    OTHER = "other"


class LaborRateUnit(enum.StrEnum):
    PER_SQUARE = "per_square"
    PER_LINEAR_FOOT = "per_linear_foot"
    PER_HOUR = "per_hour"
    FLAT_RATE = "flat_rate"


class LaborRate(BaseModel, TenantMixin):
    """Labor rate by task type, with regional and crew-size adjustments."""

    __tablename__ = "labor_rates"

    task_type: Mapped[LaborTaskType] = mapped_column(
        Enum(LaborTaskType, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)

    rate_unit: Mapped[LaborRateUnit] = mapped_column(
        Enum(LaborRateUnit, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    base_rate: Mapped[float] = mapped_column(Float, nullable=False)

    # Adjustments
    crew_size_standard: Mapped[int] = mapped_column(Integer, default=3)
    crew_size_adjustment_pct: Mapped[float] = mapped_column(Float, default=0.0)
    region_adjustment_pct: Mapped[float] = mapped_column(Float, default=0.0)
    markup_pct: Mapped[float] = mapped_column(Float, default=0.0)

    rate_card_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rate_card_versions.id")
    )

    is_active: Mapped[bool] = mapped_column(default=True)


# ---------------------------------------------------------------------------
# Permit Fees — jurisdiction-based lookup
# ---------------------------------------------------------------------------


class PermitFee(BaseModel, TenantMixin):
    """Permit fee by jurisdiction (ZIP code or city/county)."""

    __tablename__ = "permit_fees"

    zip_code: Mapped[str | None] = mapped_column(String(10), index=True)
    city: Mapped[str | None] = mapped_column(String(100))
    county: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2), nullable=False)

    permit_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g., "roofing", "siding"
    base_fee: Mapped[float] = mapped_column(Float, nullable=False)
    per_sqft_fee: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(default=True)
