"""Lifecycle regression tests — full end-to-end scenario validation.

Phase 5: Verifies the complete project lifecycle from lead through warranty,
ensuring all agent handoffs, event emissions, and state transitions work
correctly across the entire pipeline.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.events import EventType
from app.agents.graphs.lead_onboarding import (
    LeadState,
    classify_intent,
    _normalize_project_type,
)
from app.agents.graphs.orchestrator import OrchestratorState, decide_next_action
from app.agents.graphs.payment_closure import (
    PaymentState,
    determine_payment_action,
    generate_warranty,
    route_after_determine,
)
from app.agents.graphs.progress_qc import _get_expected_work
from app.agents.graphs.project_execution import evaluate_schedule
from app.integrations.llm.router import LLMResponse
from app.integrations.stripe.payments import build_payment_schedule


# ---------------------------------------------------------------------------
# Full lifecycle: Lead → Estimate → Schedule → Execute → QC → Pay → Warranty
# ---------------------------------------------------------------------------

class TestFullLifecycleRegression:
    """Walk through the complete lifecycle, verifying each transition."""

    # Step 1: Lead classification
    @pytest.mark.asyncio
    async def test_step1_lead_classification(self):
        with patch("app.agents.graphs.lead_onboarding.llm_router") as mock:
            mock.complete = AsyncMock(return_value=LLMResponse(
                content="new_lead",
                model="test", input_tokens=50, output_tokens=5, latency_ms=100,
            ))
            mock.classify = AsyncMock(return_value="new_lead")

            state: LeadState = {
                "company_id": "co-1", "customer_phone": "+15551234567",
                "from_phone": "+15559999999", "current_input": "I need a new roof",
                "media_urls": [], "conversation_history": [],
                "intent": "", "sentiment": "neutral",
                "project_type": "", "property_address": "",
                "photo_analysis": {}, "estimated_sqft": 0.0,
                "estimate_result": {}, "response_text": "",
                "needs_human_review": False, "human_review_reason": "",
                "confidence": 0.0, "project_id": "",
            }
            result = await classify_intent(state)
            assert result["intent"] == "new_lead"

    # Step 2: Project type normalization
    def test_step2_project_type_normalization(self):
        assert _normalize_project_type("roof replacement") == "roof_replacement"
        assert _normalize_project_type("new roof") == "roof_replacement"
        assert _normalize_project_type("siding") == "siding_install"

    # Step 3: Estimate (payment schedule built correctly)
    def test_step3_payment_schedule(self):
        schedule = build_payment_schedule(15000, [
            {"name": "Contract Signing"},
            {"name": "Tear-off Complete"},
            {"name": "Shingles Installed"},
            {"name": "Final Walkthrough"},
        ])
        assert len(schedule) == 4
        total = sum(s["amount"] for s in schedule)
        assert total == 15000
        assert schedule[0]["percentage"] == 50  # Deposit

    # Step 4: Execution — weather check
    @pytest.mark.asyncio
    async def test_step4_weather_check_clear(self):
        state = {
            "weather_safe": True,
            "weather_alerts": [],
            "forecast": [
                {"date": "2026-04-15", "is_workable": True, "conditions": "Clear"},
                {"date": "2026-04-16", "is_workable": True, "conditions": "Clear"},
            ],
            "scheduled_start": "2026-04-15T08:00:00Z",
        }
        result = await evaluate_schedule(state)
        assert result.get("proposed_date", "") == ""  # No reschedule needed

    # Step 5: QC expectations per milestone
    def test_step5_qc_expectations(self):
        for milestone, keywords in [
            ("Tear-off Complete", ["deck", "removed"]),
            ("Shingles Installed", ["shingle", "nailing"]),
            ("Final Walkthrough", ["complete"]),
        ]:
            expected = _get_expected_work(milestone, None)
            for kw in keywords:
                assert kw in expected.lower(), f"'{kw}' not in expectations for '{milestone}'"

    # Step 6: Orchestrator routes approved milestone → payment
    @pytest.mark.asyncio
    async def test_step6_approval_to_payment(self):
        mock_response = LLMResponse(
            content="AGENT: payment\nREASONING: Approved milestone triggers payment\nCONFIDENCE: 0.95\nNEEDS_ESCALATION: no",
            model="test", input_tokens=150, output_tokens=25, latency_ms=200,
        )
        with patch("app.agents.graphs.orchestrator.llm_router") as mock:
            mock.complete = AsyncMock(return_value=mock_response)

            state: OrchestratorState = {
                "company_id": "co-1", "project_id": "p-1",
                "trigger_event": {
                    "event_type": EventType.MILESTONE_HUMAN_APPROVED.value,
                    "data": {"milestone": "Final Walkthrough"},
                },
                "trigger_type": EventType.MILESTONE_HUMAN_APPROVED.value,
                "project_status": "in_progress",
                "project_type": "roof_replacement",
                "milestones": [
                    {"name": "Tear-off Complete", "status": "approved"},
                    {"name": "Shingles Installed", "status": "approved"},
                    {"name": "Final Walkthrough", "status": "approved"},
                ],
                "recent_events": [],
                "next_agent": "", "agent_input": {},
                "decision_reasoning": "", "confidence": 0.0,
                "actions_taken": [], "events_emitted": [],
                "needs_human_escalation": False, "escalation_reason": "",
            }
            result = await decide_next_action(state)
            assert result["next_agent"] == "payment"

    # Step 7: Final payment
    @pytest.mark.asyncio
    async def test_step7_final_payment_determination(self):
        state: PaymentState = {
            "company_id": "co-1", "project_id": "p-1",
            "trigger": {
                "event_type": EventType.JOB_COMPLETED.value,
                "data": {},
            },
            "project_status": "completed",
            "contract_amount": 15000, "amount_paid": 13500,
            "amount_due": 1500, "customer_phone": "+15551234567",
            "customer_email": "", "from_phone": "+15559999999",
            "property_address": "456 Maple Dr",
            "payment_schedule": [],
            "current_milestone_payment": {},
            "days_overdue": 0,
            "actions": [], "events_to_emit": [], "messages_to_send": [],
        }
        result = await determine_payment_action(state)
        payment = result["current_milestone_payment"]
        assert payment["type"] == "final_invoice"
        assert payment["amount"] == 1500

    # Step 8: Warranty generation after full payment
    @pytest.mark.asyncio
    async def test_step8_warranty_on_full_payment(self):
        mock_response = LLMResponse(
            content="5-Year Workmanship Warranty for 456 Maple Dr...",
            model="test", input_tokens=100, output_tokens=100, latency_ms=300,
        )
        with patch("app.agents.graphs.payment_closure.llm_router") as mock:
            mock.complete = AsyncMock(return_value=mock_response)

            state: PaymentState = {
                "company_id": "co-1", "project_id": "p-1",
                "trigger": {}, "project_status": "completed",
                "contract_amount": 15000, "amount_paid": 15000,
                "amount_due": 0, "customer_phone": "+15551234567",
                "customer_email": "", "from_phone": "+15559999999",
                "property_address": "456 Maple Dr",
                "payment_schedule": [],
                "current_milestone_payment": {"type": "none"},
                "days_overdue": 0,
                "actions": [], "events_to_emit": [], "messages_to_send": [],
            }
            result = await generate_warranty(state)

            assert any(a["action"] == "warranty_generated" for a in result.get("actions", []))
            assert any(a["action"] == "followups_scheduled" for a in result.get("actions", []))
            assert len(result.get("messages_to_send", [])) > 0
            assert len(result.get("events_to_emit", [])) > 0


# ---------------------------------------------------------------------------
# Event type completeness — ensure all lifecycle events exist
# ---------------------------------------------------------------------------

class TestEventTypeCompleteness:
    """Verify all expected lifecycle event types exist."""

    LIFECYCLE_EVENTS = [
        # Lead
        "lead_created", "lead_qualified", "estimate_generated",
        "contract_sent", "contract_signed",
        # Execution
        "job_scheduled", "job_rescheduled", "weather_alert",
        "crew_dispatched", "crew_arrived",
        "material_ordered", "material_delayed",
        # QC
        "milestone_started", "milestone_photo_uploaded",
        "milestone_qc_passed", "milestone_qc_failed",
        "milestone_human_approval_requested",
        "milestone_human_approved", "milestone_human_rejected",
        # Payments
        "invoice_sent", "payment_received",
        "payment_reminder_sent", "payment_overdue",
        # Closure
        "job_completed", "warranty_generated",
        # Phase 4 additions
        "change_order_requested", "change_order_approved", "change_order_rejected",
        "measurement_ordered", "measurement_received",
        "drone_survey_requested", "drone_survey_completed",
        "price_update_applied", "price_update_flagged",
        # System
        "human_escalation", "agent_error",
        "customer_message", "crew_message",
    ]

    def test_all_lifecycle_events_exist(self):
        """Every expected event type must be defined in EventType enum."""
        event_values = {e.value for e in EventType}
        for expected in self.LIFECYCLE_EVENTS:
            assert expected in event_values, f"Missing EventType: {expected}"

    def test_event_count(self):
        """Verify we have the expected number of event types."""
        assert len(EventType) >= 35  # Should have 35+ event types


# ---------------------------------------------------------------------------
# Graph construction regression
# ---------------------------------------------------------------------------

class TestGraphConstructionRegression:
    """Verify all agent graphs still build correctly after Phase 5 changes."""

    def test_orchestrator_graph_builds(self):
        from app.agents.graphs.orchestrator import build_orchestrator_graph
        graph = build_orchestrator_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_payment_graph_builds(self):
        from app.agents.graphs.payment_closure import build_payment_graph
        graph = build_payment_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_qc_graph_builds(self):
        from app.agents.graphs.progress_qc import build_qc_graph
        graph = build_qc_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_engagement_graph_builds(self):
        from app.agents.graphs.customer_engagement import build_customer_engagement_graph
        graph = build_customer_engagement_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_execution_graph_builds(self):
        from app.agents.graphs.project_execution import build_execution_graph
        graph = build_execution_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_lead_graph_builds(self):
        from app.agents.graphs.lead_onboarding import build_lead_onboarding_graph
        graph = build_lead_onboarding_graph()
        compiled = graph.compile()
        assert compiled is not None
