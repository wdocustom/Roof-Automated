"""Twilio SMS/MMS sending — thin wrapper with retry logic."""

import asyncio
import functools

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
from twilio.rest import Client

from app.core.config import settings

logger = structlog.get_logger()

_twilio_client: Client | None = None


def _get_client() -> Client:
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _twilio_client


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def send_sms(
    to: str,
    from_: str | None = None,
    body: str = "",
    media_urls: list[str] | None = None,
) -> str:
    """Send an SMS/MMS via Twilio. Returns the message SID.

    Uses messaging_service_sid if no from_ is provided (recommended for 10DLC).
    """
    client = _get_client()

    kwargs: dict = {"to": to, "body": body}

    if from_:
        kwargs["from_"] = from_
    elif settings.twilio_messaging_service_sid:
        kwargs["messaging_service_sid"] = settings.twilio_messaging_service_sid

    if media_urls:
        kwargs["media_url"] = media_urls

    logger.info("twilio_send_sms", to=to, from_=from_, body_len=len(body))

    # Twilio's Python SDK is synchronous — run in executor to avoid blocking
    loop = asyncio.get_event_loop()
    message = await loop.run_in_executor(
        None, functools.partial(client.messages.create, **kwargs)
    )

    logger.info("twilio_send_sms_ok", sid=message.sid, to=to)
    return message.sid
