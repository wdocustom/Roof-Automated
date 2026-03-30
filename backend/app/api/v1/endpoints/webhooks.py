"""Twilio webhook endpoints — the entry point for all inbound SMS/MMS.

These endpoints receive Twilio's HTTP callbacks, validate signatures,
and dispatch to Temporal workflows for async processing. The webhook
MUST respond within 15 seconds — all heavy processing happens in Temporal.
"""

import hashlib
import hmac

from fastapi import APIRouter, Form, HTTPException, Request, status
from twilio.request_validator import RequestValidator

from app.core.config import settings
from app.workflows.sms_intake import start_sms_intake_workflow

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _validate_twilio_signature(request: Request, body: bytes) -> bool:
    """Validate that the request genuinely came from Twilio."""
    if settings.environment == "development":
        return True  # Skip in dev for easier testing

    signature = request.headers.get("X-Twilio-Signature", "")
    validator = RequestValidator(settings.twilio_auth_token)

    # Reconstruct the full URL Twilio used
    url = str(request.url)
    # Parse form params for validation
    params = dict(x.split("=", 1) for x in body.decode().split("&")) if body else {}

    return validator.validate(url, params, signature)


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
    Returns a minimal TwiML response to acknowledge receipt.
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

    # Check for STOP/HELP keywords (TCPA compliance — handle before any processing)
    body_upper = Body.strip().upper() if Body else ""
    if body_upper in ("STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"):
        # Temporal workflow will handle opt-out recording
        await start_sms_intake_workflow(
            message_sid=MessageSid,
            from_phone=From,
            to_phone=To,
            body=Body,
            media_urls=media_urls,
            is_opt_out=True,
        )
        # Twilio auto-handles STOP responses, but we record it
        return {"status": "opt_out_recorded"}

    if body_upper in ("HELP", "INFO"):
        await start_sms_intake_workflow(
            message_sid=MessageSid,
            from_phone=From,
            to_phone=To,
            body=Body,
            media_urls=media_urls,
            is_help_request=True,
        )
        return {"status": "help_queued"}

    # Normal message — dispatch to Temporal for async processing
    workflow_id = await start_sms_intake_workflow(
        message_sid=MessageSid,
        from_phone=From,
        to_phone=To,
        body=Body,
        media_urls=media_urls,
    )

    return {"status": "accepted", "workflow_id": workflow_id}


@router.post("/twilio/status")
async def twilio_status_callback(
    request: Request,
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
):
    """Receive delivery status updates from Twilio (sent, delivered, failed, etc.)."""
    # TODO: Update message status in DB via lightweight query (no Temporal needed)
    return {"status": "ok"}
