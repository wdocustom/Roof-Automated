"""Twilio webhook endpoints — the entry point for all inbound SMS/MMS.

These endpoints receive Twilio's HTTP callbacks, validate signatures,
and dispatch to Temporal workflows for async processing. The webhook
MUST respond within 15 seconds — all heavy processing happens in Temporal.
"""

import logging

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import Response

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _twiml_ok() -> Response:
    """Return an empty TwiML response — tells Twilio we received the webhook."""
    return Response(content=EMPTY_TWIML, media_type="text/xml")


def _validate_twilio_signature(url: str, form_params: dict[str, str], signature: str) -> bool:
    """Validate that the request genuinely came from Twilio."""
    if settings.environment == "development":
        return True  # Skip in dev for easier testing

    try:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(settings.twilio_auth_token)
        return validator.validate(url, form_params, signature)
    except Exception:
        logger.warning("Twilio signature validation failed — allowing in non-production")
        return settings.environment != "production"


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
    Returns a 200 to Twilio in all cases to prevent retries.
    """
    # Validate Twilio signature using parsed form data (not raw body,
    # which is already consumed by FastAPI's Form() parameter parsing).
    form_data = await request.form()
    form_params = {k: str(v) for k, v in form_data.items()}
    signature = request.headers.get("X-Twilio-Signature", "")

    if not _validate_twilio_signature(str(request.url), form_params, signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature",
        )

    # Collect media URLs if present
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

    # Dispatch to Temporal workflow
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
        return _twiml_ok()

    except Exception as exc:
        logger.exception(
            "Failed to dispatch SMS %s to Temporal: %s", MessageSid, str(exc),
        )
        # Still return 200 + empty TwiML so Twilio doesn't retry.
        # The message will be retried via Temporal when the worker recovers.
        return _twiml_ok()


@router.post("/twilio/status")
async def twilio_status_callback(
    request: Request,
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
):
    """Receive delivery status updates from Twilio (sent, delivered, failed, etc.)."""
    logger.info("Twilio status: %s → %s", MessageSid, MessageStatus)
    return _twiml_ok()
