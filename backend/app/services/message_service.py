"""Message storage and retrieval service."""

from sqlalchemy import select

from app.core.database import get_system_session, get_tenant_session
from app.models.message import Message, MessageDirection, MessageMedia, MessageSenderType
from app.models.user import User


async def store_message(
    message_sid: str,
    from_phone: str,
    to_phone: str,
    body: str,
    media_urls: list[dict],
) -> dict:
    """Store an inbound message. Returns message_id, company_id, customer_id.

    Uses system session first to look up tenant by phone number,
    then stores under the correct tenant context.
    """
    company_id = ""
    customer_id = None

    # Look up which company owns the 'to' phone number, and which customer is texting
    async with get_system_session() as session:
        # Find company by Twilio phone number
        from app.models.company import Company

        result = await session.execute(
            select(Company).where(Company.twilio_phone_number == to_phone)
        )
        company = result.scalar_one_or_none()
        if company:
            company_id = company.clerk_org_id

        # Find customer by phone
        if company_id:
            result = await session.execute(
                select(User).where(User.phone == from_phone, User.company_id == company_id)
            )
            customer = result.scalar_one_or_none()
            if customer:
                customer_id = str(customer.id)

    if not company_id:
        # Unknown number — store with empty company_id for manual review
        company_id = "__unknown__"

    # Store the message under tenant context
    async with get_tenant_session(company_id) as session:
        message = Message(
            company_id=company_id,
            from_phone=from_phone,
            to_phone=to_phone,
            body=body,
            direction=MessageDirection.INBOUND,
            sender_type=MessageSenderType.CUSTOMER,
            twilio_message_sid=message_sid,
            twilio_status="received",
        )
        session.add(message)
        await session.flush()

        # Store media attachments
        for media in media_urls:
            attachment = MessageMedia(
                company_id=company_id,
                message_id=message.id,
                media_url=media["url"],
                content_type=media.get("content_type", "application/octet-stream"),
            )
            session.add(attachment)

        await session.flush()

        return {
            "message_id": str(message.id),
            "company_id": company_id,
            "customer_id": customer_id,
        }
