"""Drone Survey Integration — partner dispatch and data ingestion.

Phase 4: Manages drone survey requests for complex or large properties.
Dispatches to drone survey partner companies via API, tracks flight
status, and ingests the resulting measurement/imagery data.

Typical flow:
  1. Agent determines drone survey is needed (complex roof, large property)
  2. DroneService submits survey request to partner
  3. Partner flies property, uploads data
  4. Webhook notifies us → data parsed into PropertyMeasurement
  5. Orchestrator triggers re-estimation with drone data

Partner integrations are abstracted — initially supports a generic
webhook-based partner API, extensible for specific providers.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

import httpx
import structlog

from app.core.config import settings
from app.integrations.eagleview.client import (
    MeasurementSource,
    PropertyMeasurement,
    RoofFacet,
)

logger = structlog.get_logger()


class DronePartner(StrEnum):
    GENERIC = "generic"
    # Future: DRONEBASE = "dronebase"
    # Future: ZEITVIEW = "zeitview"


class SurveyStatus(StrEnum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    SCHEDULED = "scheduled"
    IN_FLIGHT = "in_flight"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SurveyPriority(StrEnum):
    STANDARD = "standard"  # 3-5 business days
    RUSH = "rush"  # 1-2 business days
    EMERGENCY = "emergency"  # Same day (storm damage)


@dataclass
class DroneSurveyRequest:
    """Request for a drone survey."""

    request_id: str = ""
    partner: DronePartner = DronePartner.GENERIC
    address: str = ""
    project_id: str = ""
    company_id: str = ""
    priority: SurveyPriority = SurveyPriority.STANDARD
    status: SurveyStatus = SurveyStatus.REQUESTED
    survey_type: str = "roof_inspection"  # roof_inspection, full_property, damage_assessment
    notes: str = ""
    requested_at: str = ""
    scheduled_for: str | None = None
    completed_at: str | None = None
    report_url: str | None = None


class DroneService:
    """Manages drone survey requests and partner communication."""

    def __init__(self, partner_api_url: str = "", partner_api_key: str = ""):
        self.partner_api_url = partner_api_url or getattr(settings, "drone_partner_api_url", "")
        self.partner_api_key = partner_api_key or getattr(settings, "drone_partner_api_key", "")

    async def request_survey(
        self,
        address: str,
        project_id: str,
        company_id: str = "",
        priority: SurveyPriority = SurveyPriority.STANDARD,
        survey_type: str = "roof_inspection",
        notes: str = "",
    ) -> DroneSurveyRequest:
        """Submit a drone survey request to the partner.

        Returns immediately with request_id. Completion is async via webhook.
        """
        request = DroneSurveyRequest(
            address=address,
            project_id=project_id,
            company_id=company_id,
            priority=priority,
            survey_type=survey_type,
            notes=notes,
            requested_at=datetime.now(UTC).isoformat(),
        )

        if not self.partner_api_url:
            logger.warning("drone_partner_not_configured", address=address)
            request.request_id = f"mock-drone-{project_id[:8]}"
            request.status = SurveyStatus.REQUESTED
            return request

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.partner_api_url}/surveys",
                headers={"Authorization": f"Bearer {self.partner_api_key}"},
                json={
                    "address": address,
                    "survey_type": survey_type,
                    "priority": priority.value,
                    "notes": notes,
                    "callback_url": f"{settings.api_v1_prefix}/webhooks/drone/survey",
                    "metadata": {
                        "project_id": project_id,
                        "company_id": company_id,
                    },
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()

        request.request_id = data.get("request_id", "")
        request.status = SurveyStatus.ACCEPTED

        logger.info(
            "drone_survey_requested",
            request_id=request.request_id,
            address=address,
            priority=priority.value,
        )

        return request

    async def check_survey_status(self, request_id: str) -> DroneSurveyRequest:
        """Check status of an existing survey request."""
        if not self.partner_api_url:
            return DroneSurveyRequest(
                request_id=request_id,
                status=SurveyStatus.REQUESTED,
            )

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.partner_api_url}/surveys/{request_id}",
                headers={"Authorization": f"Bearer {self.partner_api_key}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

        status_map = {
            "requested": SurveyStatus.REQUESTED,
            "accepted": SurveyStatus.ACCEPTED,
            "scheduled": SurveyStatus.SCHEDULED,
            "in_flight": SurveyStatus.IN_FLIGHT,
            "processing": SurveyStatus.PROCESSING,
            "completed": SurveyStatus.COMPLETED,
            "cancelled": SurveyStatus.CANCELLED,
            "failed": SurveyStatus.FAILED,
        }

        return DroneSurveyRequest(
            request_id=request_id,
            status=status_map.get(data.get("status", ""), SurveyStatus.REQUESTED),
            address=data.get("address", ""),
            scheduled_for=data.get("scheduled_for"),
            completed_at=data.get("completed_at"),
            report_url=data.get("report_url"),
        )

    async def parse_survey_report(self, report_data: dict) -> PropertyMeasurement:
        """Parse a completed drone survey report into PropertyMeasurement."""
        measurements = report_data.get("measurements", {})
        imagery = report_data.get("imagery", {})

        facets = []
        for f in measurements.get("facets", []):
            facets.append(
                RoofFacet(
                    facet_id=str(f.get("id", "")),
                    area_sqft=f.get("area_sqft", 0),
                    pitch=f.get("pitch", ""),
                    pitch_degrees=f.get("pitch_degrees", 0),
                )
            )

        total_sqft = measurements.get("total_roof_sqft", 0)

        return PropertyMeasurement(
            address=report_data.get("address", ""),
            source=MeasurementSource.DRONE,
            total_roof_sqft=total_sqft,
            total_roof_squares=round(total_sqft / 100, 1) if total_sqft else None,
            predominant_pitch=measurements.get("predominant_pitch"),
            steepest_pitch=measurements.get("steepest_pitch"),
            roof_facets=facets,
            num_facets=len(facets),
            ridge_length_ft=measurements.get("ridge_length_ft"),
            hip_length_ft=measurements.get("hip_length_ft"),
            valley_length_ft=measurements.get("valley_length_ft"),
            eave_length_ft=measurements.get("eave_length_ft"),
            rake_length_ft=measurements.get("rake_length_ft"),
            drip_edge_length_ft=measurements.get("drip_edge_length_ft"),
            flashing_length_ft=measurements.get("flashing_length_ft"),
            stories=measurements.get("stories"),
            building_height_ft=measurements.get("building_height_ft"),
            report_id=report_data.get("survey_id"),
            report_url=imagery.get("orthomosaic_url"),
            completed_at=report_data.get("completed_at"),
            confidence=0.96,  # Drone surveys are high accuracy
            raw_data=report_data,
        )


def should_request_drone_survey(
    roof_complexity: str,
    total_sqft: float | None,
    stories: int | None = None,
    has_eagleview: bool = False,
) -> bool:
    """Determine if a drone survey should be requested for this property.

    Criteria:
    - Very complex roofs (many facets, steep pitches)
    - Large properties (>4000 sqft roof)
    - Potential storm damage requiring detailed assessment
    - No existing EagleView report available
    """
    if has_eagleview:
        return False

    if roof_complexity == "very_complex":
        return True

    if total_sqft and total_sqft > 4000:
        return True

    return bool(stories and stories >= 3)


# Default service
drone_service = DroneService()
