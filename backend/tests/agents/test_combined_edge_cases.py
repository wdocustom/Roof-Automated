"""Combined edge case tests — multiple simultaneous issues.

Phase 5: Tests realistic scenarios where multiple things go wrong at once.
The swarm must handle compound situations gracefully without deadlocks,
dropped events, or conflicting actions.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.events import EventType
from app.agents.graphs.orchestrator import OrchestratorState, decide_next_action
from app.agents.graphs.payment_closure import (
    PaymentState,
    determine_payment_action,
    route_after_determine,
    send_reminder,
)
from app.integrations.llm.router import LLMResponse
from app.integrations.stripe.payments import get_reminder_tone
from app.integrations.weather.client import _is_workable_day

# ---------------------------------------------------------------------------
# Scenario: Weather delay + overdue payment + change order
# ---------------------------------------------------------------------------


class TestCompoundWeatherPayment:
    """Weather delay hits during an overdue payment situation."""

    @pytest.mark.asyncio
    async def test_weather_takes_priority_over_payment(self):
        """When weather is dangerous, execution agent takes priority."""
        mock_response = LLMResponse(
            content="AGENT: execution\nREASONING: Weather safety takes priority over payment concerns\nCONFIDENCE: 0.9\nNEEDS_ESCALATION: no",
            model="test",
            input_tokens=200,
            output_tokens=30,
            latency_ms=250,
        )

        with patch("app.agents.graphs.orchestrator.llm_router") as mock:
            mock.complete = AsyncMock(return_value=mock_response)

            state: OrchestratorState = {
                "company_id": "co-1",
                "project_id": "p-1",
                "trigger_event": {
                    "event_type": EventType.WEATHER_ALERT.value,
                    "data": {"alert": "severe_thunderstorm", "wind_speed": 50},
                },
                "trigger_type": EventType.WEATHER_ALERT.value,
                "project_status": "in_progress",
                "project_type": "roof_replacement",
                "milestones": [{"name": "Shingles Installed", "status": "in_progress"}],
                "recent_events": [
                    {
                        "event_type": "payment_overdue",
                        "description": "$4250 overdue 5 days",
                        "agent_name": "payment",
                    },
                ],
                "next_agent": "",
                "agent_input": {},
                "decision_reasoning": "",
                "confidence": 0.0,
                "actions_taken": [],
                "events_emitted": [],
                "needs_human_escalation": False,
                "escalation_reason": "",
            }
            result = await decide_next_action(state)
            assert result["next_agent"] == "execution"

    @pytest.mark.asyncio
    async def test_overdue_30_days_escalates_to_human(self):
        """30+ days overdue should escalate regardless of other issues."""
        cadence = get_reminder_tone(30)
        assert cadence["tone"] == "escalate"
        assert cadence["channel"] == "human"


# ---------------------------------------------------------------------------
# Scenario: QC failure + material price spike + customer complaint
# ---------------------------------------------------------------------------


class TestCompoundQCPricingCustomer:
    """QC fails while materials spike and customer is upset."""

    @pytest.mark.asyncio
    async def test_qc_failure_routes_correctly(self):
        mock_response = LLMResponse(
            content="AGENT: qc\nREASONING: QC failure needs immediate attention before any pricing discussion\nCONFIDENCE: 0.88\nNEEDS_ESCALATION: no",
            model="test",
            input_tokens=200,
            output_tokens=30,
            latency_ms=250,
        )

        with patch("app.agents.graphs.orchestrator.llm_router") as mock:
            mock.complete = AsyncMock(return_value=mock_response)

            state: OrchestratorState = {
                "company_id": "co-1",
                "project_id": "p-1",
                "trigger_event": {
                    "event_type": EventType.MILESTONE_QC_FAILED.value,
                    "data": {
                        "milestone": "Shingles Installed",
                        "issues": ["misalignment", "exposed nails"],
                    },
                },
                "trigger_type": EventType.MILESTONE_QC_FAILED.value,
                "project_status": "in_progress",
                "project_type": "roof_replacement",
                "milestones": [
                    {"name": "Tear-off Complete", "status": "approved"},
                    {"name": "Shingles Installed", "status": "awaiting_qc"},
                ],
                "recent_events": [
                    {
                        "event_type": "price_update_flagged",
                        "description": "Shingles +15%",
                        "agent_name": "supplier_webhook",
                    },
                    {
                        "event_type": "customer_message",
                        "description": "Why is this taking so long?",
                        "agent_name": "engagement",
                    },
                ],
                "next_agent": "",
                "agent_input": {},
                "decision_reasoning": "",
                "confidence": 0.0,
                "actions_taken": [],
                "events_emitted": [],
                "needs_human_escalation": False,
                "escalation_reason": "",
            }
            result = await decide_next_action(state)
            assert result["next_agent"] == "qc"


# ---------------------------------------------------------------------------
# Scenario: Multiple weather borderline days
# ---------------------------------------------------------------------------


class TestWeatherBorderline:
    """Test borderline weather conditions across multiple dimensions."""

    def test_borderline_wind_and_rain(self):
        """Both wind and rain at thresholds — should be cautious."""
        # Wind at 25 (threshold) + rain at 40% (threshold) = risky combo
        assert _is_workable_day(precip_chance=40, wind_speed=25, temp_high=72, temp_low=55) is True
        # Just over either threshold
        assert _is_workable_day(precip_chance=41, wind_speed=25, temp_high=72, temp_low=55) is False
        assert _is_workable_day(precip_chance=40, wind_speed=26, temp_high=72, temp_low=55) is False

    def test_extreme_heat(self):
        """Over 105F should prevent work."""
        assert _is_workable_day(precip_chance=0, wind_speed=5, temp_high=106, temp_low=85) is False
        assert _is_workable_day(precip_chance=0, wind_speed=5, temp_high=105, temp_low=85) is True

    def test_borderline_cold(self):
        """35F temp_low threshold for cold (shingles brittle below 35F)."""
        assert _is_workable_day(precip_chance=0, wind_speed=5, temp_high=50, temp_low=34) is False
        assert _is_workable_day(precip_chance=0, wind_speed=5, temp_high=50, temp_low=35) is True


# ---------------------------------------------------------------------------
# Scenario: Payment with zero balance edge cases
# ---------------------------------------------------------------------------


class TestPaymentEdgeCases:
    """Test payment agent edge cases."""

    @pytest.mark.asyncio
    async def test_invoice_with_zero_amount(self):
        """Should not send an invoice for $0."""
        from app.agents.graphs.payment_closure import send_invoice

        state: PaymentState = {
            "company_id": "co-1",
            "project_id": "p-1",
            "trigger": {},
            "project_status": "in_progress",
            "contract_amount": 10000,
            "amount_paid": 10000,
            "amount_due": 0,
            "customer_phone": "+15551234567",
            "customer_email": "",
            "from_phone": "+15559999999",
            "property_address": "123 Oak St",
            "payment_schedule": [],
            "current_milestone_payment": {"type": "milestone_invoice", "amount": 0},
            "days_overdue": 0,
            "actions": [],
            "events_to_emit": [],
            "messages_to_send": [],
        }
        result = await send_invoice(state)
        assert not result.get("messages_to_send", [])

    @pytest.mark.asyncio
    async def test_reminder_with_no_phone(self):
        """Should not crash when customer has no phone."""
        state: PaymentState = {
            "company_id": "co-1",
            "project_id": "p-1",
            "trigger": {},
            "project_status": "in_progress",
            "contract_amount": 10000,
            "amount_paid": 0,
            "amount_due": 10000,
            "customer_phone": "",
            "customer_email": "",
            "from_phone": "",
            "property_address": "123 Oak St",
            "payment_schedule": [],
            "current_milestone_payment": {"type": "reminder", "amount": 10000},
            "days_overdue": 5,
            "actions": [],
            "events_to_emit": [],
            "messages_to_send": [],
        }
        result = await send_reminder(state)
        assert not result.get("messages_to_send", [])

    def test_fully_paid_routes_to_warranty(self):
        state: PaymentState = {
            "company_id": "co-1",
            "project_id": "p-1",
            "trigger": {},
            "project_status": "completed",
            "contract_amount": 10000,
            "amount_paid": 10000,
            "amount_due": 0,
            "customer_phone": "+15551234567",
            "customer_email": "",
            "from_phone": "+15559999999",
            "property_address": "123 Oak St",
            "payment_schedule": [],
            "current_milestone_payment": {"type": "none"},
            "days_overdue": 0,
            "actions": [],
            "events_to_emit": [],
            "messages_to_send": [],
        }
        assert route_after_determine(state) == "warranty"

    @pytest.mark.asyncio
    async def test_escalate_reminder_at_30_days(self):
        """30+ days overdue should escalate, not send another SMS."""
        state: PaymentState = {
            "company_id": "co-1",
            "project_id": "p-1",
            "trigger": {},
            "project_status": "invoiced",
            "contract_amount": 10000,
            "amount_paid": 0,
            "amount_due": 10000,
            "customer_phone": "+15551234567",
            "customer_email": "",
            "from_phone": "+15559999999",
            "property_address": "123 Oak St",
            "payment_schedule": [],
            "current_milestone_payment": {"type": "reminder", "amount": 10000},
            "days_overdue": 35,
            "actions": [],
            "events_to_emit": [],
            "messages_to_send": [],
        }
        result = await send_reminder(state)
        # Should escalate, not send SMS
        assert any("escalate" in str(a.get("action", "")) for a in result.get("actions", []))
        assert not result.get("messages_to_send", [])


# ---------------------------------------------------------------------------
# Scenario: Rapid-fire milestone completions
# ---------------------------------------------------------------------------


class TestRapidMilestones:
    """Test handling multiple milestones completing in quick succession."""

    @pytest.mark.asyncio
    async def test_sequential_milestone_payments(self):
        """Each milestone should get its own payment action."""
        for milestone in ["Tear-off Complete", "Shingles Installed", "Final Walkthrough"]:
            state: PaymentState = {
                "company_id": "co-1",
                "project_id": "p-1",
                "trigger": {
                    "event_type": EventType.MILESTONE_QC_PASSED.value,
                    "data": {"milestone": milestone},
                },
                "project_status": "in_progress",
                "contract_amount": 10000,
                "amount_paid": 0,
                "amount_due": 10000,
                "customer_phone": "+15551234567",
                "customer_email": "",
                "from_phone": "+15559999999",
                "property_address": "123 Oak St",
                "payment_schedule": [
                    {"milestone": "Tear-off Complete", "amount": 5000},
                    {"milestone": "Shingles Installed", "amount": 4000},
                    {"milestone": "Final Walkthrough", "amount": 1000},
                ],
                "current_milestone_payment": {},
                "days_overdue": 0,
                "actions": [],
                "events_to_emit": [],
                "messages_to_send": [],
            }
            result = await determine_payment_action(state)
            payment = result.get("current_milestone_payment", {})
            assert payment["type"] == "milestone_invoice"
            assert milestone in payment["description"]


# ---------------------------------------------------------------------------
# Scenario: Change order during active work
# ---------------------------------------------------------------------------


class TestChangeOrderScenario:
    """Test that change orders are properly escalated."""

    @pytest.mark.asyncio
    async def test_change_order_escalates(self):
        mock_response = LLMResponse(
            content="AGENT: escalate\nREASONING: Change orders require human judgment on scope and pricing\nCONFIDENCE: 0.4\nNEEDS_ESCALATION: yes",
            model="test",
            input_tokens=200,
            output_tokens=30,
            latency_ms=250,
        )

        with patch("app.agents.graphs.orchestrator.llm_router") as mock:
            mock.complete = AsyncMock(return_value=mock_response)

            state: OrchestratorState = {
                "company_id": "co-1",
                "project_id": "p-1",
                "trigger_event": {
                    "event_type": EventType.CHANGE_ORDER_REQUESTED.value,
                    "data": {
                        "requested_by": "customer",
                        "description": "Add skylight to the roof",
                        "estimated_impact": 3000,
                    },
                },
                "trigger_type": EventType.CHANGE_ORDER_REQUESTED.value,
                "project_status": "in_progress",
                "project_type": "roof_replacement",
                "milestones": [
                    {"name": "Tear-off Complete", "status": "approved"},
                    {"name": "Shingles Installed", "status": "in_progress"},
                ],
                "recent_events": [],
                "next_agent": "",
                "agent_input": {},
                "decision_reasoning": "",
                "confidence": 0.0,
                "actions_taken": [],
                "events_emitted": [],
                "needs_human_escalation": False,
                "escalation_reason": "",
            }
            result = await decide_next_action(state)
            assert result["needs_human_escalation"] is True

    def test_change_order_event_types_exist(self):
        assert EventType.CHANGE_ORDER_REQUESTED.value == "change_order_requested"
        assert EventType.CHANGE_ORDER_APPROVED.value == "change_order_approved"
        assert EventType.CHANGE_ORDER_REJECTED.value == "change_order_rejected"
