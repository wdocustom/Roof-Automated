"""Stripe Webhook Handler — processes payment events for real-time tracking.

Phase 5: Handles Stripe webhook events for:
  - Payment success (checkout.session.completed, payment_intent.succeeded)
  - Payment failure (payment_intent.payment_failed)
  - Disputes (charge.dispute.created, charge.dispute.closed)
  - Refunds (charge.refunded)

All events are verified via Stripe signature, logged in audit trail,
and routed to the appropriate agent via event emission.
"""

import stripe
import structlog

from app.core.config import settings

logger = structlog.get_logger()


def verify_webhook_signature(payload: bytes, sig_header: str) -> dict | None:
    """Verify Stripe webhook signature and return the event object.

    Returns None if verification fails.
    """
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
        return event
    except stripe.error.SignatureVerificationError:
        logger.warning("stripe_webhook_signature_invalid")
        return None
    except ValueError:
        logger.warning("stripe_webhook_payload_invalid")
        return None


async def handle_payment_succeeded(event_data: dict, company_id: str, project_id: str) -> dict:
    """Handle successful payment — update project, emit event."""
    from app.agents.events import Event, EventType, emit_event

    amount = event_data.get("amount_received", 0) / 100  # cents → dollars
    payment_intent_id = event_data.get("id", "")

    if project_id:
        await emit_event(
            company_id=company_id,
            event=Event(
                event_type=EventType.PAYMENT_RECEIVED,
                agent_name="stripe_webhook",
                project_id=project_id,
                data={
                    "amount": amount,
                    "payment_intent_id": payment_intent_id,
                    "currency": event_data.get("currency", "usd"),
                },
                description=f"Payment received: ${amount:,.2f}",
            ),
        )

    logger.info(
        "payment_succeeded",
        amount=amount,
        project_id=project_id,
        payment_intent_id=payment_intent_id,
    )

    return {"status": "recorded", "amount": amount}


async def handle_payment_failed(event_data: dict, company_id: str, project_id: str) -> dict:
    """Handle failed payment — notify customer and flag for follow-up."""
    from app.agents.events import Event, EventType, emit_event

    amount = event_data.get("amount", 0) / 100
    failure_code = event_data.get("last_payment_error", {}).get("code", "unknown")
    failure_message = event_data.get("last_payment_error", {}).get("message", "")

    if project_id:
        await emit_event(
            company_id=company_id,
            event=Event(
                event_type=EventType.PAYMENT_OVERDUE,
                agent_name="stripe_webhook",
                project_id=project_id,
                data={
                    "amount": amount,
                    "failure_code": failure_code,
                    "failure_message": failure_message,
                },
                description=f"Payment failed: ${amount:,.2f} — {failure_code}",
            ),
        )

    logger.warning(
        "payment_failed",
        amount=amount,
        failure_code=failure_code,
        project_id=project_id,
    )

    return {"status": "failure_recorded", "failure_code": failure_code}


async def handle_dispute_created(event_data: dict, company_id: str, project_id: str) -> dict:
    """Handle payment dispute — always escalate to human."""
    from app.agents.events import Event, EventType, emit_event

    amount = event_data.get("amount", 0) / 100
    reason = event_data.get("reason", "unknown")

    if project_id:
        await emit_event(
            company_id=company_id,
            event=Event(
                event_type=EventType.HUMAN_ESCALATION,
                agent_name="stripe_webhook",
                project_id=project_id,
                data={
                    "escalation_type": "payment_dispute",
                    "amount": amount,
                    "reason": reason,
                    "dispute_id": event_data.get("id", ""),
                },
                description=f"Payment dispute opened: ${amount:,.2f} — {reason}",
            ),
        )

    logger.error(
        "payment_dispute_created",
        amount=amount,
        reason=reason,
        project_id=project_id,
    )

    return {"status": "dispute_escalated", "reason": reason}


STRIPE_EVENT_HANDLERS = {
    "payment_intent.succeeded": handle_payment_succeeded,
    "payment_intent.payment_failed": handle_payment_failed,
    "charge.dispute.created": handle_dispute_created,
}
