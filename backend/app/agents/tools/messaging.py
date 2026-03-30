"""Messaging tools for LangGraph agents — send SMS and manage conversations."""

from langchain_core.tools import tool

from app.integrations.twilio.sms import send_sms


@tool
async def send_text_message(
    to_phone: str,
    body: str,
    from_phone: str | None = None,
    media_urls: list[str] | None = None,
) -> dict:
    """Send an SMS/MMS message to a customer or crew member.

    Args:
        to_phone: Recipient phone number in E.164 format.
        body: Message text (max 1600 chars for SMS, longer for MMS).
        from_phone: Optional sender number. Uses messaging service if omitted.
        media_urls: Optional list of media URLs for MMS.

    Returns:
        Dict with message_sid and status.
    """
    sid = await send_sms(
        to=to_phone,
        from_=from_phone,
        body=body,
        media_urls=media_urls,
    )
    return {"message_sid": sid, "status": "sent"}


@tool
async def send_payment_link(
    to_phone: str,
    amount_cents: int,
    description: str,
    from_phone: str | None = None,
) -> dict:
    """Send a Stripe payment link via SMS to the customer.

    Args:
        to_phone: Customer phone number.
        amount_cents: Payment amount in cents (e.g., 500000 = $5,000).
        description: What the payment is for.
        from_phone: Optional sender number.

    Returns:
        Dict with payment_url and message_sid.
    """
    from app.integrations.stripe.payments import create_payment_link

    payment_url = await create_payment_link(
        amount_cents=amount_cents,
        description=description,
    )

    body = (
        f"Your payment of ${amount_cents / 100:,.2f} for {description} is ready.\n"
        f"Pay securely here: {payment_url}\n\n"
        f"Reply HELP for assistance or STOP to opt out."
    )

    sid = await send_sms(to=to_phone, from_=from_phone, body=body)
    return {"payment_url": payment_url, "message_sid": sid, "status": "sent"}
