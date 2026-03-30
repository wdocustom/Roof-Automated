"""Tests for Stripe payments — payment scheduling, reminders, and webhooks.

Phase 5: Covers payment schedule generation, reminder cadence,
milestone invoicing, and webhook event handling.
"""

import pytest

from app.integrations.stripe.payments import (
    REMINDER_CADENCE,
    build_payment_schedule,
    get_reminder_tone,
)


class TestPaymentSchedule:
    def test_single_milestone(self):
        schedule = build_payment_schedule(10000, [{"name": "Complete"}])
        assert len(schedule) == 1
        assert schedule[0]["amount"] == 10000
        assert schedule[0]["percentage"] == 100

    def test_two_milestones(self):
        schedule = build_payment_schedule(10000, [
            {"name": "Deposit"},
            {"name": "Final"},
        ])
        assert len(schedule) == 2
        assert schedule[0]["percentage"] == 60
        assert schedule[1]["percentage"] == 40
        assert schedule[0]["amount"] + schedule[1]["amount"] == 10000

    def test_three_milestones(self):
        schedule = build_payment_schedule(10000, [
            {"name": "Deposit"},
            {"name": "Shingles Installed"},
            {"name": "Final Walkthrough"},
        ])
        assert len(schedule) == 3
        assert schedule[0]["percentage"] == 50  # Deposit
        assert schedule[2]["percentage"] == 10  # Final
        total = sum(s["amount"] for s in schedule)
        assert total == 10000

    def test_four_milestones(self):
        schedule = build_payment_schedule(20000, [
            {"name": "Deposit"},
            {"name": "Tear-off Complete"},
            {"name": "Shingles Installed"},
            {"name": "Final"},
        ])
        assert len(schedule) == 4
        assert schedule[0]["percentage"] == 50
        assert schedule[-1]["percentage"] == 10

    def test_no_milestones(self):
        schedule = build_payment_schedule(5000, [])
        assert len(schedule) == 1
        assert schedule[0]["amount"] == 5000

    def test_zero_amount(self):
        schedule = build_payment_schedule(0, [{"name": "Test"}])
        assert schedule[0]["amount"] == 0


class TestReminderCadence:
    def test_day_1_is_friendly(self):
        result = get_reminder_tone(1)
        assert result["tone"] == "friendly"

    def test_day_5_is_firm(self):
        result = get_reminder_tone(5)
        assert result["tone"] == "firm"

    def test_day_10_is_urgent(self):
        result = get_reminder_tone(10)
        assert result["tone"] == "urgent"

    def test_day_21_is_final(self):
        result = get_reminder_tone(21)
        assert result["tone"] == "final"

    def test_day_30_escalates(self):
        result = get_reminder_tone(30)
        assert result["tone"] == "escalate"
        assert result["channel"] == "human"

    def test_day_0_defaults_to_friendly(self):
        result = get_reminder_tone(0)
        assert result["tone"] == "friendly"

    def test_cadence_is_monotonically_escalating(self):
        """Ensure days_overdue thresholds increase monotonically."""
        prev = 0
        for entry in REMINDER_CADENCE:
            assert entry["days_overdue"] >= prev
            prev = entry["days_overdue"]


class TestStripeWebhookHandlers:
    @pytest.mark.asyncio
    async def test_payment_succeeded_handler(self):
        from app.integrations.stripe.webhooks import handle_payment_succeeded
        from unittest.mock import AsyncMock, patch

        with patch("app.agents.events.emit_event", new_callable=AsyncMock):
            result = await handle_payment_succeeded(
                {"amount_received": 500000, "id": "pi_test", "currency": "usd"},
                company_id="co-1",
                project_id="p-1",
            )
            assert result["status"] == "recorded"
            assert result["amount"] == 5000.0

    @pytest.mark.asyncio
    async def test_payment_failed_handler(self):
        from app.integrations.stripe.webhooks import handle_payment_failed
        from unittest.mock import AsyncMock, patch

        with patch("app.agents.events.emit_event", new_callable=AsyncMock):
            result = await handle_payment_failed(
                {
                    "amount": 500000,
                    "last_payment_error": {"code": "card_declined", "message": "Insufficient funds"},
                },
                company_id="co-1",
                project_id="p-1",
            )
            assert result["status"] == "failure_recorded"
            assert result["failure_code"] == "card_declined"

    @pytest.mark.asyncio
    async def test_dispute_always_escalates(self):
        from app.integrations.stripe.webhooks import handle_dispute_created
        from unittest.mock import AsyncMock, patch

        with patch("app.agents.events.emit_event", new_callable=AsyncMock) as mock_emit:
            result = await handle_dispute_created(
                {"amount": 800000, "reason": "product_not_received", "id": "dp_test"},
                company_id="co-1",
                project_id="p-1",
            )
            assert result["status"] == "dispute_escalated"
            # Verify it emitted a HUMAN_ESCALATION event
            call_kwargs = mock_emit.call_args
            assert call_kwargs[1]["event"].event_type.value == "human_escalation"
