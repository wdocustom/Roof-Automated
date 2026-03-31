"""Stripe webhook endpoint — receives payment events from Stripe.

Phase 5: Handles payment success, failure, and dispute events.
Verifies webhook signature, extracts project metadata, and routes
to the appropriate handler.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(request: Request):
    """Receive webhook events from Stripe.

    Handles:
      - payment_intent.succeeded — record payment, update project
      - payment_intent.payment_failed — flag for follow-up
      - charge.dispute.created — always escalate to human
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    from app.integrations.stripe.webhooks import (
        STRIPE_EVENT_HANDLERS,
        verify_webhook_signature,
    )

    event = verify_webhook_signature(payload, sig_header)
    if event is None:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event.get("type", "")
    event_data = event.get("data", {}).get("object", {})

    # Extract project/company from metadata
    metadata = event_data.get("metadata", {})
    company_id = metadata.get("company_id", "")
    project_id = metadata.get("project_id", "")

    logger.info("stripe_webhook: %s (company=%s, project=%s)", event_type, company_id, project_id)

    handler = STRIPE_EVENT_HANDLERS.get(event_type)
    if handler:
        try:
            result = await handler(event_data, company_id, project_id)
            return {"status": "processed", "event_type": event_type, **result}
        except Exception:
            logger.exception("stripe_webhook: handler failed for %s", event_type)
            return {"status": "error", "event_type": event_type}

    # Unhandled event type — acknowledge but don't process
    return {"status": "ignored", "event_type": event_type}
