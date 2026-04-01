"""Twilio webhook endpoints — the entry point for all inbound SMS/MMS.

These endpoints receive Twilio's HTTP callbacks, validate signatures,
and dispatch to Temporal workflows for async processing. The webhook
MUST respond within 15 seconds — all heavy processing happens in Temporal.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Form, HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _validate_twilio_signature(request: Request, body: bytes) -> bool:
    """Validate that the request genuinely came from Twilio."""
    if settings.environment == "development":
        return True  # Skip in dev for easier testing

    try:
        from twilio.request_validator import RequestValidator

        signature = request.headers.get("X-Twilio-Signature", "")
        validator = RequestValidator(settings.twilio_auth_token)

        # Reconstruct the full URL Twilio used
        url = str(request.url)
        # Parse form params for validation
        params = dict(x.split("=", 1) for x in body.decode().split("&")) if body else {}

        return validator.validate(url, params, signature)
    except Exception:
        logger.warning("Twilio signature validation failed — allowing in non-production")
        return settings.environment != "production"


async def _store_message_directly(
    message_sid: str,
    from_phone: str,
    to_phone: str,
    body: str,
    media_urls: list[dict],
) -> str | None:
    """Fallback: store the inbound message directly in the DB when Temporal is unavailable."""
    try:
        from app.core.database import get_tenant_session
        from app.models.message import Message, MessageChannel, MessageDirection, MessageSenderType

        # Use "unassigned" as company_id — RLS requires matching session var
        async with get_tenant_session("unassigned") as session:
            msg_id = uuid.uuid4()
            msg = Message(
                id=msg_id,
                company_id="unassigned",
                from_phone=from_phone,
                to_phone=to_phone,
                direction=MessageDirection.INBOUND,
                sender_type=MessageSenderType.CUSTOMER,
                body=body,
                channel=MessageChannel.SMS,
                twilio_message_sid=message_sid,
                twilio_status="received",
            )
            session.add(msg)
            logger.info("Stored message %s directly (Temporal unavailable)", message_sid)
            return str(msg_id)
    except Exception:
        logger.exception("Failed to store message directly for %s", message_sid)
        return None


@router.post("/twilio/sms")
async def twilio_sms_webhook(
    request: Request,
    MessageSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(default=""),
    NumMedia: int = Form(default=0),
):
    """Receive inbound SMS/MMS from Twilio.

    Validates signature, then dispatches to a Temporal workflow for processing.
    Falls back to direct DB storage if Temporal is unavailable.
    Returns a 200 to Twilio in all cases to prevent retries.
    """
    # Validate Twilio signature
    raw_body = await request.body()
    if not _validate_twilio_signature(request, raw_body):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature",
        )

    # Collect media URLs if present
    form_data = await request.form()
    media_urls = []
    for i in range(NumMedia):
        url = form_data.get(f"MediaUrl{i}")
        content_type = form_data.get(f"MediaContentType{i}")
        if url:
            media_urls.append({"url": str(url), "content_type": str(content_type or "")})

    logger.info(
        "Inbound SMS: from=%s to=%s body=%s media=%d",
        From, To, Body[:50] if Body else "(empty)", len(media_urls),
    )

    # Check for STOP/HELP keywords (TCPA compliance)
    body_upper = Body.strip().upper() if Body else ""

    # Try Temporal workflow first, fall back to direct storage
    try:
        from app.workflows.sms_intake import start_sms_intake_workflow

        is_opt_out = body_upper in ("STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT")
        is_help = body_upper in ("HELP", "INFO")

        workflow_id = await start_sms_intake_workflow(
            message_sid=MessageSid,
            from_phone=From,
            to_phone=To,
            body=Body,
            media_urls=media_urls,
            is_opt_out=is_opt_out,
            is_help_request=is_help,
        )

        logger.info("SMS dispatched to Temporal: workflow_id=%s", workflow_id)

        if is_opt_out:
            return {"status": "opt_out_recorded"}
        if is_help:
            return {"status": "help_queued"}
        return {"status": "accepted", "workflow_id": workflow_id}

    except Exception:
        logger.warning(
            "Temporal unavailable for SMS %s — storing directly", MessageSid, exc_info=True
        )

        # Fallback: store message directly so it's not lost
        msg_id = await _store_message_directly(
            message_sid=MessageSid,
            from_phone=From,
            to_phone=To,
            body=Body,
            media_urls=media_urls,
        )

        return {
            "status": "stored_fallback",
            "message_id": msg_id,
            "note": "Temporal unavailable — message stored for later processing",
        }


@router.post("/twilio/status")
async def twilio_status_callback(
    request: Request,
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
):
    """Receive delivery status updates from Twilio (sent, delivered, failed, etc.)."""
    logger.info("Twilio status: %s → %s", MessageSid, MessageStatus)
    return {"status": "ok"}
