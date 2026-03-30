"""Tests for the Customer Engagement Agent."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.graphs.customer_engagement import (
    EngagementState,
    build_customer_engagement_graph,
    classify_and_respond,
)
from app.integrations.llm.router import LLMResponse


class TestCustomerEngagement:
    @pytest.mark.asyncio
    async def test_handles_scheduling_question(self):
        mock_response = LLMResponse(
            content=(
                "INTENT: scheduling\n"
                "RESPONSE: Your crew is scheduled for this Thursday at 8am! We'll text you a reminder the night before.\n"
                "NEEDS_ESCALATION: no\n"
                "ESCALATION_REASON: \n"
                "UPSELL: \n"
                "CONFIDENCE: 0.9"
            ),
            model="test",
            input_tokens=200,
            output_tokens=50,
            latency_ms=500,
        )

        with patch("app.agents.graphs.customer_engagement.llm_router") as mock_router:
            mock_router.complete = AsyncMock(return_value=mock_response)

            state: EngagementState = {
                "company_id": "test-co",
                "customer_phone": "+15551234567",
                "from_phone": "+15559876543",
                "project_id": "test-project-id",
                "messages": [],
                "current_input": "When is the crew coming?",
                "media_urls": [],
                "project_context": {"status": "scheduled", "project_type": "roof_replacement"},
                "intent": "",
                "response_text": "",
                "upsell_offered": "",
                "needs_escalation": False,
                "escalation_reason": "",
                "confidence": 0.0,
            }

            result = await classify_and_respond(state)
            assert result["intent"] == "scheduling"
            assert not result["needs_escalation"]
            assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_escalates_complaint(self):
        mock_response = LLMResponse(
            content=(
                "INTENT: complaint\n"
                "RESPONSE: I'm sorry to hear about that. Let me connect you with a manager right away.\n"
                "NEEDS_ESCALATION: yes\n"
                "ESCALATION_REASON: Customer complaint about work quality\n"
                "UPSELL: \n"
                "CONFIDENCE: 0.95"
            ),
            model="test",
            input_tokens=200,
            output_tokens=50,
            latency_ms=500,
        )

        with patch("app.agents.graphs.customer_engagement.llm_router") as mock_router:
            mock_router.complete = AsyncMock(return_value=mock_response)

            state: EngagementState = {
                "company_id": "test-co",
                "customer_phone": "+15551234567",
                "from_phone": "+15559876543",
                "project_id": "test-project-id",
                "messages": [],
                "current_input": "The shingles are already coming loose after 2 weeks!",
                "media_urls": [],
                "project_context": {"status": "completed"},
                "intent": "",
                "response_text": "",
                "upsell_offered": "",
                "needs_escalation": False,
                "escalation_reason": "",
                "confidence": 0.0,
            }

            result = await classify_and_respond(state)
            assert result["needs_escalation"] is True
            assert "complaint" in result["escalation_reason"].lower()

    @pytest.mark.asyncio
    async def test_identifies_upsell_opportunity(self):
        mock_response = LLMResponse(
            content=(
                "INTENT: question\n"
                "RESPONSE: Your standard shingles come with a 25-year warranty. Great protection!\n"
                "NEEDS_ESCALATION: no\n"
                "ESCALATION_REASON: \n"
                "UPSELL: ice and water shield upgrade\n"
                "CONFIDENCE: 0.85"
            ),
            model="test",
            input_tokens=200,
            output_tokens=50,
            latency_ms=500,
        )

        with patch("app.agents.graphs.customer_engagement.llm_router") as mock_router:
            mock_router.complete = AsyncMock(return_value=mock_response)

            state: EngagementState = {
                "company_id": "test-co",
                "customer_phone": "+15551234567",
                "from_phone": "+15559876543",
                "project_id": "test-project-id",
                "messages": [],
                "current_input": "What kind of warranty do the shingles have?",
                "media_urls": [],
                "project_context": {"status": "contract_signed"},
                "intent": "",
                "response_text": "",
                "upsell_offered": "",
                "needs_escalation": False,
                "escalation_reason": "",
                "confidence": 0.0,
            }

            result = await classify_and_respond(state)
            assert result["upsell_offered"] == "ice and water shield upgrade"


class TestGraphConstruction:
    def test_engagement_graph_builds(self):
        graph = build_customer_engagement_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_engagement_graph_has_expected_nodes(self):
        graph = build_customer_engagement_graph()
        node_names = set(graph.nodes.keys())
        expected = {"load_context", "classify_respond", "upsell", "respond", "escalate"}
        assert expected.issubset(node_names)
