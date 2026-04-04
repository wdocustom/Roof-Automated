"""Twilio phone number provisioning for new company onboarding.

Searches for available local numbers in a given area code and purchases one,
then creates/updates a Messaging Service and configures the webhook URL.
"""

import asyncio
import functools

import structlog
from twilio.rest import Client

from app.core.config import settings

logger = structlog.get_logger()


def _get_client() -> Client:
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


async def search_available_numbers(
    area_code: str | None = None,
    state: str | None = None,
    country: str = "US",
    limit: int = 5,
) -> list[dict]:
    """Search for available local phone numbers.

    Returns a list of dicts with 'phone_number', 'friendly_name', 'locality',
    'region', and 'capabilities'.
    """
    client = _get_client()

    kwargs: dict = {"limit": limit, "sms_enabled": True, "mms_enabled": True}
    if area_code:
        kwargs["area_code"] = area_code
    if state:
        kwargs["in_region"] = state

    loop = asyncio.get_event_loop()
    numbers = await loop.run_in_executor(
        None,
        functools.partial(
            client.available_phone_numbers(country).local.list, **kwargs
        ),
    )

    return [
        {
            "phone_number": n.phone_number,
            "friendly_name": n.friendly_name,
            "locality": n.locality,
            "region": n.region,
            "capabilities": {
                "sms": n.capabilities.get("sms", False),
                "mms": n.capabilities.get("mms", False),
                "voice": n.capabilities.get("voice", False),
            },
        }
        for n in numbers
    ]


async def purchase_phone_number(phone_number: str) -> dict:
    """Purchase a phone number and configure its SMS webhook.

    Returns dict with 'sid', 'phone_number', and 'friendly_name'.
    """
    client = _get_client()
    webhook_url = f"https://roof-automated-production.up.railway.app/api/v1/webhooks/twilio/sms"
    status_url = f"https://roof-automated-production.up.railway.app/api/v1/webhooks/twilio/status"

    loop = asyncio.get_event_loop()
    number = await loop.run_in_executor(
        None,
        functools.partial(
            client.incoming_phone_numbers.create,
            phone_number=phone_number,
            sms_url=webhook_url,
            sms_method="POST",
            status_callback=status_url,
            status_callback_method="POST",
        ),
    )

    logger.info(
        "twilio_number_purchased",
        sid=number.sid,
        phone_number=number.phone_number,
    )

    return {
        "sid": number.sid,
        "phone_number": number.phone_number,
        "friendly_name": number.friendly_name,
    }


async def create_messaging_service(
    company_name: str, phone_number_sid: str
) -> str:
    """Create a Twilio Messaging Service and attach the phone number.

    Returns the Messaging Service SID.
    """
    client = _get_client()
    webhook_url = f"https://roof-automated-production.up.railway.app/api/v1/webhooks/twilio/sms"
    loop = asyncio.get_event_loop()

    # Create the messaging service
    service = await loop.run_in_executor(
        None,
        functools.partial(
            client.messaging.v1.services.create,
            friendly_name=f"Roof Automated - {company_name}",
            inbound_request_url=webhook_url,
            inbound_method="POST",
            fallback_url=webhook_url,
            fallback_method="POST",
        ),
    )

    # Attach the phone number to the service
    await loop.run_in_executor(
        None,
        functools.partial(
            client.messaging.v1.services(service.sid).phone_numbers.create,
            phone_number_sid=phone_number_sid,
        ),
    )

    logger.info(
        "twilio_messaging_service_created",
        service_sid=service.sid,
        phone_number_sid=phone_number_sid,
        company=company_name,
    )

    return service.sid


async def provision_number_for_company(
    company_name: str,
    area_code: str | None = None,
    state: str | None = None,
) -> dict:
    """Full provisioning flow: search → buy → create messaging service.

    Returns dict with 'phone_number', 'phone_number_sid',
    'messaging_service_sid'.
    """
    # 1. Find available numbers
    numbers = await search_available_numbers(
        area_code=area_code, state=state, limit=1
    )
    if not numbers:
        raise ValueError(
            f"No available numbers found for area_code={area_code}, state={state}"
        )

    chosen = numbers[0]

    # 2. Purchase the number
    purchase = await purchase_phone_number(chosen["phone_number"])

    # 3. Create messaging service and attach number
    messaging_sid = await create_messaging_service(
        company_name=company_name,
        phone_number_sid=purchase["sid"],
    )

    return {
        "phone_number": purchase["phone_number"],
        "phone_number_sid": purchase["sid"],
        "messaging_service_sid": messaging_sid,
    }
