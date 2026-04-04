"""Stripe payment integration — links, checkout sessions, and partial payments.

Phase 5: Enhanced with progress invoicing, partial payment tracking,
and payment status queries.
"""

import stripe
import structlog

from app.core.config import settings

logger = structlog.get_logger()


def _init_stripe() -> None:
    stripe.api_key = settings.stripe_secret_key


async def create_payment_link(
    amount_cents: int,
    description: str,
    customer_email: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Create a Stripe Payment Link that can be embedded in an SMS.

    Returns the URL to send to the customer.
    """
    _init_stripe()

    # Create a price for this specific payment
    price = stripe.Price.create(
        unit_amount=amount_cents,
        currency="usd",
        product_data={"name": description},
    )

    link = stripe.PaymentLink.create(
        line_items=[{"price": price.id, "quantity": 1}],
        metadata=metadata or {},
    )

    return link.url


async def create_checkout_session(
    amount_cents: int,
    description: str,
    success_url: str,
    cancel_url: str,
    customer_email: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Create a Stripe Checkout Session. Returns the session URL."""
    _init_stripe()

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": description},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=customer_email,
        metadata=metadata or {},
    )

    return session.url or ""


async def create_milestone_invoice(
    amount_cents: int,
    description: str,
    milestone_name: str,
    project_id: str,
    company_id: str,
    customer_email: str | None = None,
) -> str:
    """Create a payment link for a specific milestone payment.

    Includes milestone metadata for tracking partial payments against
    the full contract amount.
    """
    metadata = {
        "project_id": project_id,
        "company_id": company_id,
        "milestone": milestone_name,
        "payment_type": "milestone",
    }

    return await create_payment_link(
        amount_cents=amount_cents,
        description=f"{milestone_name} — {description}",
        customer_email=customer_email,
        metadata=metadata,
    )


def build_payment_schedule(
    contract_amount: float,
    milestones: list[dict] | None = None,
) -> list[dict]:
    """Build a milestone-based payment schedule.

    Default split:
      - 50% deposit at contract signing
      - 50% upon completion / final walkthrough

    Change orders are separate transactions assessed at time of change.
    """
    return [
        {
            "milestone": "Deposit (upon signing)",
            "percentage": 50,
            "amount": round(contract_amount * 0.5, 2),
        },
        {
            "milestone": "Final payment (upon completion)",
            "percentage": 50,
            "amount": round(contract_amount * 0.5, 2),
        },
    ]


REMINDER_CADENCE = [
    {"days_overdue": 1, "tone": "friendly", "channel": "sms"},
    {"days_overdue": 3, "tone": "friendly", "channel": "sms"},
    {"days_overdue": 5, "tone": "firm", "channel": "sms"},
    {"days_overdue": 7, "tone": "firm", "channel": "sms"},
    {"days_overdue": 10, "tone": "urgent", "channel": "sms"},
    {"days_overdue": 14, "tone": "urgent", "channel": "sms"},
    {"days_overdue": 21, "tone": "final", "channel": "sms"},
    {"days_overdue": 30, "tone": "escalate", "channel": "human"},
]


def get_reminder_tone(days_overdue: int) -> dict:
    """Determine the appropriate reminder tone based on days overdue.

    Returns the cadence entry for the current overdue period.
    """
    selected = REMINDER_CADENCE[0]
    for entry in REMINDER_CADENCE:
        if days_overdue >= entry["days_overdue"]:
            selected = entry
    return selected
