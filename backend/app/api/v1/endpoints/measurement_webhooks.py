"""Webhook endpoints for measurement report delivery (EagleView, Hover).

When a measurement report completes, the provider calls these webhooks.
We parse the report, update the project, and emit an event so the
Orchestrator can react (e.g., re-run estimate with real data).
"""

from fastapi import APIRouter, HTTPException, Request

from app.agents.events import Event, EventType, emit_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/eagleview/report")
async def eagleview_report_webhook(request: Request):
    """Receive completed EagleView measurement report.

    EagleView posts the report data when processing is complete.
    We parse it, store the measurements, and trigger re-estimation.
    """
    body = await request.json()
    report_id = body.get("report_id", "")
    project_id = body.get("metadata", {}).get("project_id", "")
    company_id = body.get("metadata", {}).get("company_id", "")

    if not report_id:
        raise HTTPException(status_code=400, detail="Missing report_id")

    # Parse the report
    from app.integrations.eagleview.client import EagleViewProvider

    provider = EagleViewProvider()
    measurement = await provider.parse_report(body)

    # Update project with real measurements
    if project_id and company_id:
        from app.services.measurement_service import update_project_measurements

        await update_project_measurements(
            company_id=company_id,
            project_id=project_id,
            measurement=measurement,
        )

        # Emit event so Orchestrator can trigger re-estimation
        await emit_event(
            company_id=company_id,
            event=Event(
                event_type=EventType.LEAD_QUALIFIED,
                agent_name="eagleview_webhook",
                project_id=project_id,
                data={
                    "report_id": report_id,
                    "source": "eagleview",
                    "total_sqft": measurement.total_roof_sqft,
                    "squares": measurement.total_roof_squares,
                    "num_facets": measurement.num_facets,
                    "confidence": measurement.confidence,
                },
                description=f"EagleView report received: {measurement.total_roof_sqft:.0f} sqft, {measurement.num_facets} facets",
            ),
        )

    return {"status": "received", "report_id": report_id}


@router.post("/hover/report")
async def hover_report_webhook(request: Request):
    """Receive completed Hover measurement report."""
    body = await request.json()
    job_id = body.get("job_id", "")
    project_id = body.get("metadata", {}).get("project_id", "")
    company_id = body.get("metadata", {}).get("company_id", "")

    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job_id")

    from app.integrations.eagleview.client import HoverProvider

    provider = HoverProvider()
    measurement = await provider.parse_report(body)

    if project_id and company_id:
        from app.services.measurement_service import update_project_measurements

        await update_project_measurements(
            company_id=company_id,
            project_id=project_id,
            measurement=measurement,
        )

        await emit_event(
            company_id=company_id,
            event=Event(
                event_type=EventType.LEAD_QUALIFIED,
                agent_name="hover_webhook",
                project_id=project_id,
                data={
                    "report_id": job_id,
                    "source": "hover",
                    "total_sqft": measurement.total_roof_sqft,
                    "confidence": measurement.confidence,
                },
                description=f"Hover report received: {measurement.total_roof_sqft:.0f} sqft",
            ),
        )

    return {"status": "received", "job_id": job_id}


@router.post("/drone/survey")
async def drone_survey_webhook(request: Request):
    """Receive completed drone survey report from partner.

    Drone survey partners call this webhook when a survey is complete.
    We parse the measurements, update the project, and emit an event.
    """
    body = await request.json()
    survey_id = body.get("survey_id", "")
    project_id = body.get("metadata", {}).get("project_id", "")
    company_id = body.get("metadata", {}).get("company_id", "")

    if not survey_id:
        raise HTTPException(status_code=400, detail="Missing survey_id")

    from app.integrations.drone.client import drone_service

    measurement = await drone_service.parse_survey_report(body)

    if project_id and company_id:
        from app.services.measurement_service import update_project_measurements

        await update_project_measurements(
            company_id=company_id,
            project_id=project_id,
            measurement=measurement,
        )

        await emit_event(
            company_id=company_id,
            event=Event(
                event_type=EventType.DRONE_SURVEY_COMPLETED,
                agent_name="drone_webhook",
                project_id=project_id,
                data={
                    "survey_id": survey_id,
                    "source": "drone",
                    "total_sqft": measurement.total_roof_sqft,
                    "num_facets": measurement.num_facets,
                    "confidence": measurement.confidence,
                },
                description=f"Drone survey completed: {measurement.total_roof_sqft:.0f} sqft",
            ),
        )

    return {"status": "received", "survey_id": survey_id}


@router.post("/supplier/prices")
async def supplier_price_webhook(request: Request):
    """Receive price updates from a supplier.

    Suppliers push price changes via webhook. We parse and apply
    updates to the company's rate card (auto-apply small changes,
    flag large changes for review).
    """
    body = await request.json()
    supplier_name = body.get("supplier", "generic")
    company_id = body.get("company_id", "")

    if not company_id:
        raise HTTPException(status_code=400, detail="Missing company_id")

    from app.integrations.supplier.price_feed import SupplierName, supplier_feed

    try:
        supplier = SupplierName(supplier_name)
    except ValueError:
        supplier = SupplierName.GENERIC

    updates = supplier_feed.parse_webhook_update(supplier, body)

    if updates:
        result = await supplier_feed.apply_updates(company_id, updates)

        if result.auto_applied > 0:
            await emit_event(
                company_id=company_id,
                event=Event(
                    event_type=EventType.PRICE_UPDATE_APPLIED,
                    agent_name="supplier_webhook",
                    project_id="",
                    data={
                        "supplier": supplier.value,
                        "auto_applied": result.auto_applied,
                        "flagged": result.flagged_for_review,
                    },
                    description=f"Supplier {supplier.value}: {result.auto_applied} prices auto-updated, {result.flagged_for_review} flagged",
                ),
            )

        return {
            "status": "processed",
            "auto_applied": result.auto_applied,
            "flagged_for_review": result.flagged_for_review,
            "errors": result.errors,
        }

    return {"status": "no_updates"}
