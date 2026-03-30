"""Supplier Price Feed — real-time material pricing from distributors.

Phase 4: Ingests price updates from roofing/siding suppliers (ABC Supply,
Beacon, SRS Distribution) to keep rate cards current. Supports both
pull (API polling) and push (webhook) models.

Key capabilities:
  - Poll supplier APIs for current pricing
  - Receive webhook price updates
  - Compare against existing rate card prices
  - Auto-update rate cards within configurable thresholds
  - Alert on significant price swings (>10%)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()


class SupplierName(str, Enum):
    ABC_SUPPLY = "abc_supply"
    BEACON = "beacon"
    SRS = "srs_distribution"
    GENERIC = "generic"


@dataclass
class PriceUpdate:
    """A single material price update from a supplier."""

    supplier: SupplierName
    material_sku: str
    material_name: str
    category: str  # Maps to MaterialCategory
    unit_cost: float
    unit_type: str  # bundle, roll, linear_ft, etc.
    previous_cost: float | None = None
    change_pct: float | None = None
    effective_date: str = ""
    expires_at: str | None = None


@dataclass
class PriceFeedResult:
    """Result of processing a supplier price feed."""

    supplier: SupplierName
    updates: list[PriceUpdate] = field(default_factory=list)
    auto_applied: int = 0
    flagged_for_review: int = 0
    errors: list[str] = field(default_factory=list)
    fetched_at: str = ""


class SupplierPriceFeed:
    """Manages supplier price feeds and rate card updates."""

    # Price changes beyond this threshold require human review
    AUTO_UPDATE_THRESHOLD_PCT = 10.0

    def __init__(self):
        self.suppliers: dict[SupplierName, dict] = {}

    def register_supplier(
        self,
        name: SupplierName,
        api_url: str,
        api_key: str,
    ):
        """Register a supplier for price feed polling."""
        self.suppliers[name] = {"api_url": api_url, "api_key": api_key}

    async def fetch_prices(self, supplier: SupplierName) -> list[PriceUpdate]:
        """Poll a supplier API for current prices."""
        config = self.suppliers.get(supplier)
        if not config:
            logger.warning("supplier_not_configured", supplier=supplier.value)
            return []

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{config['api_url']}/prices",
                headers={"Authorization": f"Bearer {config['api_key']}"},
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()

        updates = []
        for item in data.get("prices", []):
            updates.append(
                PriceUpdate(
                    supplier=supplier,
                    material_sku=item.get("sku", ""),
                    material_name=item.get("name", ""),
                    category=item.get("category", ""),
                    unit_cost=item.get("unit_cost", 0),
                    unit_type=item.get("unit_type", ""),
                    effective_date=item.get("effective_date", ""),
                    expires_at=item.get("expires_at"),
                )
            )

        logger.info(
            "supplier_prices_fetched",
            supplier=supplier.value,
            count=len(updates),
        )
        return updates

    def parse_webhook_update(
        self, supplier: SupplierName, payload: dict
    ) -> list[PriceUpdate]:
        """Parse a webhook price update from a supplier."""
        updates = []

        for item in payload.get("price_changes", []):
            previous = item.get("previous_cost")
            current = item.get("new_cost", 0)
            change_pct = None
            if previous and previous > 0:
                change_pct = round(((current - previous) / previous) * 100, 1)

            updates.append(
                PriceUpdate(
                    supplier=supplier,
                    material_sku=item.get("sku", ""),
                    material_name=item.get("name", ""),
                    category=item.get("category", ""),
                    unit_cost=current,
                    unit_type=item.get("unit_type", ""),
                    previous_cost=previous,
                    change_pct=change_pct,
                    effective_date=item.get("effective_date", ""),
                )
            )

        return updates

    async def apply_updates(
        self,
        company_id: str,
        updates: list[PriceUpdate],
    ) -> PriceFeedResult:
        """Apply price updates to the company's rate card.

        Auto-applies small changes (<10%). Flags large changes for review.
        """
        from sqlalchemy import select, update as sql_update

        from app.core.database import get_tenant_session
        from app.models.rate_card import Material

        result = PriceFeedResult(
            supplier=updates[0].supplier if updates else SupplierName.GENERIC,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

        async with get_tenant_session(company_id) as session:
            for price_update in updates:
                # Find matching material by SKU or name
                query = select(Material).where(Material.is_active.is_(True))

                if price_update.material_sku:
                    query = query.where(Material.sku == price_update.material_sku)
                else:
                    query = query.where(Material.name == price_update.material_name)

                mat_result = await session.execute(query.limit(1))
                material = mat_result.scalar_one_or_none()

                if not material:
                    result.errors.append(
                        f"Material not found: {price_update.material_sku or price_update.material_name}"
                    )
                    continue

                # Calculate change percentage
                if material.unit_cost > 0:
                    change_pct = abs(
                        (price_update.unit_cost - material.unit_cost) / material.unit_cost * 100
                    )
                else:
                    change_pct = 100.0

                price_update.previous_cost = material.unit_cost
                price_update.change_pct = round(change_pct, 1)

                if change_pct <= self.AUTO_UPDATE_THRESHOLD_PCT:
                    # Auto-apply small changes
                    await session.execute(
                        sql_update(Material)
                        .where(Material.id == material.id)
                        .values(unit_cost=price_update.unit_cost)
                    )
                    result.auto_applied += 1
                    logger.info(
                        "price_auto_updated",
                        material=material.name,
                        old=material.unit_cost,
                        new=price_update.unit_cost,
                        change_pct=change_pct,
                    )
                else:
                    # Flag for human review
                    result.flagged_for_review += 1
                    logger.warning(
                        "price_change_flagged",
                        material=material.name,
                        old=material.unit_cost,
                        new=price_update.unit_cost,
                        change_pct=change_pct,
                    )

                result.updates.append(price_update)

            await session.flush()

        return result


# Default service
supplier_feed = SupplierPriceFeed()
