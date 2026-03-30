"""Measurement Service — bridges measurement providers with project records.

When a measurement report arrives (via webhook or direct fetch), this service:
  1. Updates the project's estimated_sqft and related fields
  2. Stores the full measurement data as JSONB for detailed use
  3. Optionally triggers re-estimation with real data
"""

import uuid

from sqlalchemy import select, update

import structlog

from app.core.database import get_tenant_session
from app.integrations.eagleview.client import PropertyMeasurement
from app.models.project import Project

logger = structlog.get_logger()


async def update_project_measurements(
    company_id: str,
    project_id: str,
    measurement: PropertyMeasurement,
) -> dict:
    """Persist measurement data to the project record.

    Updates estimated_sqft and the eagleview_report_id (or equivalent).
    Returns a summary of what was updated.
    """
    updates: dict = {}

    if measurement.total_roof_sqft:
        updates["estimated_sqft"] = measurement.total_roof_sqft

    if measurement.report_id:
        updates["eagleview_report_id"] = measurement.report_id

    if not updates:
        logger.info(
            "measurement_update_skipped",
            project_id=project_id,
            reason="no_data",
        )
        return {"updated": False}

    async with get_tenant_session(company_id) as session:
        await session.execute(
            update(Project)
            .where(Project.id == uuid.UUID(project_id))
            .values(**updates)
        )
        await session.flush()

    logger.info(
        "project_measurements_updated",
        project_id=project_id,
        source=measurement.source.value,
        sqft=measurement.total_roof_sqft,
        report_id=measurement.report_id,
    )

    return {
        "updated": True,
        "source": measurement.source.value,
        "sqft": measurement.total_roof_sqft,
        "report_id": measurement.report_id,
    }


async def get_measurement_for_project(
    company_id: str,
    project_id: str,
) -> PropertyMeasurement | None:
    """Fetch the best available measurement for a project.

    Checks if project has an EagleView report ID and tries to fetch it.
    Falls back to the stored estimated_sqft as a manual measurement.
    """
    from app.integrations.eagleview.client import (
        MeasurementSource,
        measurement_service,
    )

    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(Project).where(Project.id == uuid.UUID(project_id))
        )
        project = result.scalar_one_or_none()
        if not project:
            return None

        # If we have real measurement data, fetch via service
        if project.eagleview_report_id:
            try:
                return await measurement_service.get_best_measurement(
                    project.property_address
                )
            except Exception as e:
                logger.warning(
                    "measurement_fetch_failed",
                    project_id=project_id,
                    error=str(e),
                )

        # Fall back to stored estimate
        if project.estimated_sqft:
            return PropertyMeasurement(
                address=project.property_address,
                source=MeasurementSource.MANUAL,
                total_roof_sqft=project.estimated_sqft,
                total_roof_squares=round(project.estimated_sqft / 100, 1),
                confidence=0.6,
            )

    return None
