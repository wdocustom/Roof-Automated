"""TCPA consent management service."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import get_tenant_session
from app.models.consent import ConsentSource, ConsentStatus, SMSConsent


async def check_consent(phone: str, company_id: str) -> dict:
    """Check current consent status for a phone number."""
    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(SMSConsent)
            .where(SMSConsent.phone_number == phone)
            .order_by(SMSConsent.created_at.desc())
        )
        consent = result.scalar_one_or_none()

        if consent is None:
            return {"status": "no_record", "can_send": False}

        return {
            "status": consent.status.value,
            "can_send": consent.status == ConsentStatus.OPTED_IN,
            "consented_at": str(consent.consented_at) if consent.consented_at else None,
        }


async def record_opt_out(phone: str, company_id: str) -> None:
    """Record that a customer has opted out of SMS."""
    async with get_tenant_session(company_id) as session:
        consent = SMSConsent(
            company_id=company_id,
            phone_number=phone,
            status=ConsentStatus.OPTED_OUT,
            source=ConsentSource.TEXT_KEYWORD,
            revoked_at=datetime.now(timezone.utc),
            consent_text="Customer replied STOP",
        )
        session.add(consent)


async def record_opt_in(
    phone: str,
    company_id: str,
    source: ConsentSource,
    consent_text: str,
    ip_address: str | None = None,
    customer_id: str | None = None,
) -> None:
    """Record that a customer has opted in to SMS."""
    async with get_tenant_session(company_id) as session:
        consent = SMSConsent(
            company_id=company_id,
            phone_number=phone,
            customer_id=customer_id,
            status=ConsentStatus.OPTED_IN,
            source=source,
            consented_at=datetime.now(timezone.utc),
            consent_text=consent_text,
            ip_address=ip_address,
        )
        session.add(consent)
