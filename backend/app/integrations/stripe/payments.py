"""Stripe payment link generation — embedded in SMS for frictionless payments."""

import stripe

from app.core.config import settings


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
