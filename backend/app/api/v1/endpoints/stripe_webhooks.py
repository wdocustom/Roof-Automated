"""Stripe webhook endpoint — receives payment events from Stripe.

Phase 5: Handles payment success, failure, and dispute events.
Verifies webhook signature, extracts project metadata, and routes
to the appropriate handler.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import settings

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

    return await _process_stripe_event(event, STRIPE_EVENT_HANDLERS)


class StripeTestEvent(BaseModel):
    """Test payload for simulating Stripe webhook events without signature."""

    event_type: str = "payment_intent.succeeded"
    company_id: str = ""
    project_id: str = ""
    amount_cents: int = 500000  # $5,000


@router.post("/stripe/test")
async def stripe_webhook_test(payload: StripeTestEvent):
    """Simulate a Stripe webhook event for testing (non-production only).

    curl -X POST https://roof-automated-production.up.railway.app/api/v1/webhooks/stripe/test \\
      -H 'Content-Type: application/json' \\
      -d '{"event_type": "payment_intent.succeeded", "amount_cents": 500000}'
    """
    if settings.environment == "production":
        raise HTTPException(status_code=403, detail="Test endpoint disabled in production")

    from app.integrations.stripe.webhooks import STRIPE_EVENT_HANDLERS

    # Build a fake Stripe event structure
    event = {
        "type": payload.event_type,
        "data": {
            "object": {
                "id": "pi_test_000000000000",
                "amount": payload.amount_cents,
                "amount_received": payload.amount_cents,
                "currency": "usd",
                "metadata": {
                    "company_id": payload.company_id,
                    "project_id": payload.project_id,
                },
                "last_payment_error": {
                    "code": "card_declined",
                    "message": "Your card was declined (test)",
                },
                "reason": "fraudulent",
            }
        },
    }

    return await _process_stripe_event(event, STRIPE_EVENT_HANDLERS)


async def _process_stripe_event(event: dict, handlers: dict) -> dict:
    """Shared logic for processing a Stripe event (real or test)."""
    event_type = event.get("type", "")
    event_data = event.get("data", {}).get("object", {})

    metadata = event_data.get("metadata", {})
    company_id = metadata.get("company_id", "")
    project_id = metadata.get("project_id", "")

    logger.info("stripe_webhook: %s (company=%s, project=%s)", event_type, company_id, project_id)

    handler = handlers.get(event_type)
    if handler:
        try:
            result = await handler(event_data, company_id, project_id)
            return {"status": "processed", "event_type": event_type, **result}
        except Exception:
            logger.exception("stripe_webhook: handler failed for %s", event_type)
            return {"status": "error", "event_type": event_type}

    return {"status": "ignored", "event_type": event_type}
